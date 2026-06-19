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
REQUEST_DELAY = 1.0          # 每次请求的基础间隔（秒）
REQUEST_DELAY_JITTER = 1.5   # 随机抖动上限，实际间隔 = REQUEST_DELAY + random(0, JITTER)
LONG_REST_EVERY = 20         # 每爬取 N 页后做一次较长休息，模拟真人节奏
LONG_REST_SECONDS = 30.0     # 长休息时长（秒）
MAX_USER_PAGES = 500         # 爬取用户「全部」帖子时的安全翻页上限
RATE_LIMIT_BACKOFF = 30.0    # 检测到限流/封禁时的退避基准（秒），按指数递增
RATE_LIMIT_MAX_RETRIES = 4   # 单页遇到限流时的最大重试次数
MAX_RETRIES = 3
REQUEST_TIMEOUT = 10

# Headers
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Output
DEFAULT_OUTPUT_DIR = "./output"
