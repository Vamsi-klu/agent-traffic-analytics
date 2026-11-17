<div align="center">

<img src="https://raw.githubusercontent.com/tartini-ai/agent-traffic-analytics/v0.5.0/docs/assets/readme/crumb.png" alt="AgentCake" width="112">

# AgentCake — AI agent 流量分析

[![发行版: 下载](https://img.shields.io/badge/%E5%8F%91%E8%A1%8C%E7%89%88-%E4%B8%8B%E8%BD%BD-ff5c8a?style=flat)](https://github.com/tartini-ai/agent-traffic-analytics/releases)
[![反馈: 报告问题](https://img.shields.io/badge/%E5%8F%8D%E9%A6%88-%E6%8A%A5%E5%91%8A%E9%97%AE%E9%A2%98-ff5c8a?style=flat)](https://github.com/tartini-ai/agent-traffic-analytics/issues)
[![许可证: MIT](https://img.shields.io/badge/%E8%AE%B8%E5%8F%AF%E8%AF%81-MIT-ff5c8a?style=flat)](../../../LICENSE)

[English](../../../README.md) · **简体中文**

</div>

## 问题

你的网站访问量很大，转化率却停滞不前，甚至还在下降？这些访问里，会不会有一部分来自 AI agent？

HUMAN Security 发现，[来自 AI agent 和 agentic 浏览器的流量同比增长了 7,851%](https://www.humansecurity.com/newsroom/2026-state-of-ai-traffic-cyberthreat-benchmark-report/)。

如果分析工具无法识别这些 agent，它们的访问可能会计入真人流量，让日常报告产生误导。

## 解决方案

我们推出了 AgentCake，这是一款自托管的 AI agent 流量分析平台。它会录制每次访问，供你之后查看录制。它还会使用我们的行为模型和规则，区分 AI 驱动、真人驱动和混合会话。

使用 AgentCake 可帮助你:

1. **了解使用 AI agent 的客户是否找到了所需信息。** 查看他们访问的页面，并了解他们只是在浏览，还是已开始注册。
2. **发现 AI agent 遇到问题的环节。** 了解按其使用场景调整流程能否改善 agent 的使用体验。
3. **查看最常访问你网站的 AI agent** (例如 Claude in Chrome、Grok Bot 和 Muse)。了解如何为它们优化网站，以提高转换率。

![演示: 依次滚动浏览仪表板、查看会话列表和 Claude in Chrome 将操作交给真人的会话](https://raw.githubusercontent.com/tartini-ai/agent-traffic-analytics/v0.5.0/docs/assets/readme/demo.png)

*此录制内容来自一个测试商店。Claude in Chrome 将一件 T 恤加入购物车，然后真人接管并完成结账。*

### 仪表板预览

<!-- The line of no-break spaces under each picture keeps it this wide: without it a browser shrinks the five to fit one row instead of letting the row scroll sideways. -->
<table>
  <tr>
    <td width="720">
      <img src="https://raw.githubusercontent.com/tartini-ai/agent-traffic-analytics/v0.5.0/docs/assets/readme/preview-key-metrics.png" alt="Key metrics" width="720"><br>
      &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
    </td>
    <td width="720">
      <img src="https://raw.githubusercontent.com/tartini-ai/agent-traffic-analytics/v0.5.0/docs/assets/readme/preview-top-agents.png" alt="Top agents 和 Trends" width="720"><br>
      &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
    </td>
    <td width="720">
      <img src="https://raw.githubusercontent.com/tartini-ai/agent-traffic-analytics/v0.5.0/docs/assets/readme/preview-paths.png" alt="Paths 和 Sources" width="720"><br>
      &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
    </td>
    <td width="720">
      <img src="https://raw.githubusercontent.com/tartini-ai/agent-traffic-analytics/v0.5.0/docs/assets/readme/preview-devices.png" alt="Devices 和 Geography" width="720"><br>
      &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
    </td>
    <td width="720">
      <img src="https://raw.githubusercontent.com/tartini-ai/agent-traffic-analytics/v0.5.0/docs/assets/readme/preview-sessions.png" alt="Session replay" width="720"><br>
      &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
    </td>
  </tr>
</table>

- **区分真人、AI agent 和机器人。** AgentCake 会将每个会话归入一个分类: Human、Agent 或 Bot。AI agent 会话又分为 Agent only 和 Human + agent。
- **识别 AI agent，并标明确定程度。** 对于能识别的 agent (例如 Claude in Chrome、ChatGPT 和 Muse)，AgentCake 会显示其名称，并标记为 Verified 或 Likely。其余 agent 列为 Unnamed。
- **了解谁执行了操作，以及会话为何归入此分类。** 时间线会标记每个会话中的真人部分和 agent 部分，以及操作者切换的位置。每个分类的依据都显示在录制内容旁边。
- **按访问者类型查看流量。** 查看真人和 AI agent 各自的会话数、访问者数、页面查看次数和活动时间。还可以按路径、来源、设备和地理位置查看流量。
- **自托管且开源。** 只需一个程序和一个 SQLite 数据库，即可在你的电脑或服务器上运行。不发送遥测数据，采用 MIT 许可证。

## 安装

在一个新的空文件夹中打开 Claude Code、Codex 或其他 coding agent，然后粘贴以下说明:

```text
请使用 curl 或 GitHub CLI 安装 AgentCake 0.5.0。按照
https://raw.githubusercontent.com/tartini-ai/agent-traffic-analytics/v0.5.0/INSTALL.md
中的步骤操作。完成后，说明要打开的本地页面和连接网站的步骤。
```

Coding agent 将下载并校验发行版，启动 AgentCake，然后运行 `agentcake doctor`。接着，打开 http://127.0.0.1:7878/ 并注册。页面会引导你连接网站。

需要 macOS 或 Linux，并安装 Python 3.11 或更高版本，或者安装 uv。[`INSTALL.md`](../../../INSTALL.md) 提供了相同的手动步骤。

## 分类方式

AgentCake 会在你的电脑或服务器上检查四层证据。这些证据可用于识别 AI agent 会话和具体的 agent。

- **Name** 层会将 User-Agent 字符串中的名称与每个版本附带的 agent 列表进行比对。
- 安装在服务器上时，**Verification** 层会使用签名和公开的 IP 范围确认此名称。
- **Environment** 层会检测自动化痕迹、虚假的浏览器身份和某些 agent 添加的页面标记。
- **Behavior** 层使用行为模型分析每一次指针移动、按键和滚动。

测试数据包括 1,118 个自行录制的 AI agent 会话和 7,122 个真人会话。AgentCake 也可能判断出错，我们正在持续改进模型的表现。

有关每个数字的计算方式，请参阅 [`eval/README.md`](../../../eval/README.md)。

## 你的数据归你所有

页面脚本只会将访问数据发送到你自己的 AgentCake，AgentCake 不会发送任何使用数据。只有在你注册、更新列表或检查网站时，AgentCake 才会访问互联网。

AgentCake 不会记录以下内容: 访问者输入的内容、按键、密码、卡号、Cookie 和 IP 地址。它只保留来源页面的域名。

AgentCake 会在访问者的浏览器中保存一个随机 ID (不使用 Cookie)，以便统计访问者数。如果访问者在一年内没有再次访问，此 ID 将过期。

你的注册信息只会在你选择“Register and continue”时发送一次。即使不注册，也可以收集访问数据。

有关详细信息，请参阅 [`PRIVACY.md`](../../../PRIVACY.md)。[`docs/privacy-notice-template.md`](../../privacy-notice-template.md) 可帮助你告知访问者。

## 连接你的网站

注册后，本地页面会提供连接网站的说明:

1. 在网站的代码文件夹中打开 coding agent，然后粘贴此说明。
2. Coding agent 将询问你的网站地址以及 AgentCake 的运行位置。
3. 它在所有页面共用的布局中添加一行代码，以加载 cake.js (gzip 压缩后为 48 KB)。

对于 Next.js、Express、Flask、FastAPI、Django、PHP 和 WordPress，它还可以添加服务器中间件。你也可以手动执行相同的步骤。

对于公开网站，需要使用 Docker 或 systemd 将 AgentCake 安装在服务器上。仪表板保持私密，需要通过 SSH 隧道访问。

有关每个步骤，请参阅 [`SERVER.md`](../../../SERVER.md)。

## 帮助和参与贡献

[`docs/FAQ.md`](../../FAQ.md) 解答了常见问题。如果 AgentCake 分类有误或无法识别某个 AI agent，请[提交问题](https://github.com/tartini-ai/agent-traffic-analytics/issues/new?template=wrong_verdict.yml)并描述发生的情况。请勿粘贴访问者的数据。

规则和模型参数是 `agentcake/data/` 中的 JSON 文件。提交拉取请求时，请附上在更改前和更改后运行 `agentcake eval` 的结果。如果更改会将更多真人误判为 agent，则无法合并。

有关步骤，请参阅 [`CONTRIBUTING.md`](../../../CONTRIBUTING.md)。[`AGENTS.md`](../../../AGENTS.md) 可帮助 coding agent 处理代码。

如果发现安全漏洞，请发送电子邮件至 [admin@tartini.ai](mailto:admin@tartini.ai)，而不是在 GitHub 上提交问题。有关详细信息，请参阅 [`SECURITY.md`](../../../SECURITY.md)。

## 许可证

AgentCake 采用 MIT 许可证，版权归 Tartini AI 所有 ([`LICENSE`](../../../LICENSE))。AgentCake 附带的第三方代码保留其各自的许可证 ([`THIRD_PARTY.md`](../../../THIRD_PARTY.md))。

<sub>AgentCake 是一款独立产品，与其提及的 AI agent 和工具的制造商没有关联。AgentCake 也未获得这些制造商的认可或赞助。所有商标均归其各自所有者所有。</sub>
