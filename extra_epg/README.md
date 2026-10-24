# extra_epg - plugin hook for extra schedules (e.g. Sri Lankan channels)

Drop a Python file here (name not starting with `_`). The daily job imports it and calls:

    def fetch(now: int) -> list[dict]:
        """now = current UTC epoch seconds. Return programmes:
        [{"channel_id": "HiruTV.lk", "start": 1760000000, "stop": 1760003600, "title": "Hiru News"}, ...]"""

- `channel_id`: iptv-org channel id (the tvg-id, with or without the `@feed` suffix).
- `start` / `stop`: UTC epoch seconds. `title`: trimmed to 80 characters by the job.
- Public sources only (broadcaster websites). No logins, tokens or private data.
- These schedules take priority over every other source for the channels they cover.
- A module that raises is skipped and logged; it never fails the run.
- Use the standard library or `requests`-free `urllib` (the job installs only `aiohttp`).
