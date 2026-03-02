# RSS Feeds Configuration

## Global Finance

| Source | Feed URL | Notes |
|--------|----------|-------|
| Bloomberg Markets | https://www.bloomberg.com/feed/podcast/bloomberg-markets.xml | Markets-focused |
| Reuters Business | https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best | General business |
| WSJ Markets | https://feeds.a.dj.com/rss/RSSMarketsMain.xml | US markets focus |
| FT World | https://www.ft.com/rss/home | Global finance |
| CNBC Markets | https://www.cnbc.com/id/10000664/device/rss/rss.html | US markets |

## Politics & Geopolitics

| Source | Feed URL | Notes |
|--------|----------|-------|
| BBC World | http://feeds.bbci.co.uk/news/world/rss.xml | Global news |
| CNN World | http://rss.cnn.com/rss/edition_world.rss | US perspective |
| Al Jazeera | https://www.aljazeera.com/xml/rss/all.xml | Global south view |
| Economist World | https://www.economist.com/world/rss.xml | Analysis |

## Asia / China Focus

| Source | Feed URL | Notes |
|--------|----------|-------|
| SCMP China | https://www.scmp.com/rss/91/feed | Hong Kong view on China |
| Caixin | https://www.caixinglobal.com/rss/ | China business (may need paywall bypass) |
| Nikkei Asia | https://asia.nikkei.com/rss/feed | Japan/Asia markets |
| Reuters China | https://www.reutersagency.com/feed/?taxonomy=best-regions&post_type=best;region=china | China coverage |

## Market Data APIs

| Market | API | Endpoint |
|--------|-----|----------|
| A-shares indices | Sina | `https://hq.sinajs.cn/list=sh000001,sh000300,sz399001,sz399006` |
| US futures | Yahoo | `https://query1.finance.yahoo.com/v7/finance/quote?symbols=ES=F,NQ=F,YM=F` |
| US indices | Yahoo | `https://query1.finance.yahoo.com/v7/finance/quote?symbols=%5EGSPC,%5EIXIC,%5EDJI,%5EVIX` |
| HK indices | Yahoo | `https://query1.finance.yahoo.com/v7/quote/quote?symbols=%5EHSI,%5EHSCE` |

## Adding New Sources

1. Test feed: `curl -s "<feed_url>" | head -50`
2. Check encoding and format
3. Add to appropriate category above
4. Update `fetch_brief.py` if special parsing needed
