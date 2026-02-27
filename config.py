# API endpoints
XUEQIU_HOME = "https://xueqiu.com/"
SEARCH_STATUS_URL = "https://xueqiu.com/query/v1/symbol/search/status.json"
USER_TIMELINE_URL = "https://xueqiu.com/v4/statuses/user_timeline.json"

# Crawling parameters
MIN_REPLY_COUNT = 20
MAX_PAGES = 20
POSTS_PER_PAGE = 50
USER_POSTS_COUNT = 50

# Rate limiting
REQUEST_DELAY = 1.0
MAX_RETRIES = 3
REQUEST_TIMEOUT = 10

# Headers
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Output
DEFAULT_OUTPUT_DIR = "./output"
