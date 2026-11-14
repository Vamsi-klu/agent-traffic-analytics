# Agent Cake on a server as one container: the whole program (one process, one SQLite database) on python:3.14-slim,
# installed from the release wheel. SERVER.md, "Install with Docker", says how to build, set up and run it (S6.3).
#
# Build: put agentcake-<version>-py3-none-any.whl, checked against the release's SHA256SUMS, alone in dist/ next to
# this file, then `docker build -t agentcake .`. Nothing is compiled and nothing is downloaded besides the base image:
# the wheel has no dependencies, and .dockerignore lets only the wheel into the build.
#
# Run it on the host's network (`docker run --network host`). The local page (dashboard, sessions, replay, settings)
# listens on 127.0.0.1 only: in a network of its own that is the container's loopback, which no tunnel reaches; on
# the host's network it is the server's 127.0.0.1. The public listener binds what the public_listen setting says;
# EXPOSE names its port as SERVER.md sets it up.
#
# Modelled on PostHog 1.0.0's production.Dockerfile and .dockerignore (github.com/PostHog/posthog, tag 1.0.0, commit
# ab887730, MIT): a python -slim image, one process, one exposed port, an allow-listed build context.

ARG PYTHON_IMAGE=python:3.14-slim

# The wheel is installed in a stage of its own, so the final image does not carry the wheel file. It is installed by
# its file name: the file, checked against SHA256SUMS, is the version pin, and pip refuses two versions at once.
FROM ${PYTHON_IMAGE} AS install
COPY dist/ /tmp/wheels/
RUN python3 -m pip install --no-cache-dir --no-index --no-deps --disable-pip-version-check --root-user-action=ignore \
        --no-warn-script-location --prefix=/install /tmp/wheels/agentcake-*.whl

FROM ${PYTHON_IMAGE}
# A fixed user id, so that a host folder can be handed to the container: chown 10001:10001 <folder>.
ARG CAKE_UID=10001
ARG PUBLIC_PORT=8080
COPY --from=install /install /usr/local
RUN groupadd --gid "${CAKE_UID}" cake \
    && useradd --uid "${CAKE_UID}" --gid cake --home-dir /var/lib/cake --no-create-home --shell /usr/sbin/nologin cake \
    && install -d -o cake -g cake -m 700 /var/lib/cake
# The data folder (settings, database, the server-half secret), a volume so that it outlives the container.
ENV CAKE_HOME=/var/lib/cake
VOLUME ["/var/lib/cake"]
USER ${CAKE_UID}:${CAKE_UID}
EXPOSE ${PUBLIC_PORT}
# As PID 1, Python has no handler for SIGTERM and the kernel does not apply the default action to PID 1, so
# `docker stop` would wait and then kill; SIGINT has Python's own handler, which ends `serve`.
STOPSIGNAL SIGINT
# `agentcake status` asks the local page's /api/health on the configured port: exit 0 when it answers, 1 when not.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python3", "-I", "-m", "agentcake", "status"]
# -I: nothing is imported from the working folder or PYTHON* variables, as in deploy/cake.service.
ENTRYPOINT ["python3", "-I", "-m", "agentcake"]
CMD ["serve"]
