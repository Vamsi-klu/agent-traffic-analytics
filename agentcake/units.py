"""Unit conversions. They are fixed by definition, so they are written here as numbers, once."""

MS_PER_S = 1000  # protocol: 1 s = 1000 ms
S_PER_MIN = 60  # protocol: 1 min = 60 s
S_PER_HOUR = 3600  # protocol: 1 h = 3600 s
S_PER_DAY = 86400  # protocol: 1 day = 24 h = 86400 s
MS_PER_DAY = MS_PER_S * S_PER_DAY
BYTES_PER_MB = 1024 * 1024  # protocol: budget_mb counts mebibytes, as cake 0.3.x did
PERCENT = 100  # protocol: 1 = 100 %
