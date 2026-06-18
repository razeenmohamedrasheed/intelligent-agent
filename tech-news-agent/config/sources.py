# ─── RSS Sources ────────────────────────────────────────────────
# Direct RSS feed URLs — no auto-detection needed for these.
# Add more entries as needed. Agent will ingest all on each run.

RSS_FEEDS: list[dict] = [
    {"name": "Hugging Face",  "rss": "https://huggingface.co/blog/feed.xml"},
    {"name": "The Decoder",   "rss": "https://the-decoder.com/feed/"},
    {"name": "TechCrunch",    "rss": "https://techcrunch.com/feed/"},
    {"name": "InfoQ",         "rss": "https://feed.infoq.com/ai-ml-data-eng/"},
    {"name": "KDnuggets",     "rss": "https://kdnuggets.com/feed"},
    {"name": "VentureBeat",   "rss": "https://venturebeat.com/feed/"},
    {"name": "MarkTechPost",  "rss": "https://marktechpost.com/feed/"},
    {"name": "ByteByteGo",    "rss": "https://blog.bytebytego.com/feed"},
]

# ─── Scrape-only Sources (no RSS) ───────────────────────────────
# Add sites here that need HTML scraping fallback.
# Agent will auto-detect RSS first; scrape if not found.
SCRAPE_SOURCES: list[str] = [
    # "https://martinfowler.com",
]