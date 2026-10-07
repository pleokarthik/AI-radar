"""All runtime config comes from env (GitHub Secrets / Variables). Edit SOURCES below to tune feeds."""
import os


def env(key, default=None):
    v = os.getenv(key)
    return v if v not in (None, "") else default


# --- Telegram ---
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = env("TELEGRAM_CHANNEL_ID")        # "@your_channel" or "-100..."
TELEGRAM_ADMIN_CHAT_ID = env("TELEGRAM_ADMIN_CHAT_ID")  # your personal chat id (numeric)
AUTHOR_NAME = env("AUTHOR_NAME", "Leo")

# --- LLM providers ---
# Scorer: one cheap call per tick to tier all new items.
SCORER = env("SCORER", "claude")
# Drafters: each passing story gets one draft per provider -> A/B in your DM.
DRAFTERS = [p.strip() for p in env("DRAFTERS", "claude,jev").split(",") if p.strip()]

ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
CLAUDE_SCORE_MODEL = env("CLAUDE_SCORE_MODEL", "claude-haiku-5-5")
CLAUDE_DRAFT_MODEL = env("CLAUDE_DRAFT_MODEL", "claude-sonnet-5-5")

# Jev (Typesafe AI). Assumed OpenAI-compatible chat API; set base URL + model.
JEV_API_KEY = env("JEV_API_KEY")
JEV_BASE_URL = env("JEV_BASE_URL")
JEV_MODEL = env("JEV_MODEL")

# --- Throttles ---
MAX_ITEMS_TO_SCORE = int(env("MAX_ITEMS_TO_SCORE", "25"))
MAX_DRAFTS_PER_TICK = int(env("MAX_DRAFTS_PER_TICK", "1"))
MAX_DRAFTS_PER_DAY = int(env("MAX_DRAFTS_PER_DAY", "4"))
MIN_TIER = env("MIN_TIER", "notable")  # skip < notable < major < turning_point
HF_MIN_UPVOTES = int(env("HF_MIN_UPVOTES", "20"))
HN_MIN_POINTS = int(env("HN_MIN_POINTS", "150"))
SEEN_TTL_DAYS = 30

DRY_RUN = env("DRY_RUN", "0") == "1"
STATE_PATH = env("STATE_PATH", "state/state.json")

TIERS = ["skip", "notable", "major", "turning_point"]

# --- Sources ---
GITHUB_RELEASE_REPOS = [
    "anthropics/anthropic-sdk-python",
    "anthropics/claude-code",
    "openai/openai-python",
    "modelcontextprotocol/modelcontextprotocol",
    "langchain-ai/langgraph",
    "vllm-project/vllm",
    "huggingface/transformers",
    "ollama/ollama",
    "google-gemini/gemini-cli",
]

# RSS/Atom feeds. Verify each URL once; a broken feed is logged and skipped, never fatal.
RSS_FEEDS = {
    "OpenAI": "https://openai.com/news/rss.xml",
    "Google DeepMind": "https://deepmind.google/blog/rss.xml",
    "Hugging Face Blog": "https://huggingface.co/blog/feed.xml",
    "Google Research": "https://research.google/blog/rss/",
}

HN_KEYWORDS = ["LLM", "AI agent", "Claude", "GPT", "Gemini", "open-weight", "MCP", "RAG", "inference"]
