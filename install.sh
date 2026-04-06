#!/usr/bin/env bash
# =============================================================
#  LLM 知识库 — 一键安装 & 启动脚本
#  支持：macOS (Homebrew) | Linux (apt / dnf / pacman)
#
#  用法：
#    bash install.sh          # 首次安装 + 配置 + 启动
#    bash install.sh --start  # 已安装，直接启动
#    bash install.sh --config # 重新配置（不重装依赖）
# =============================================================

set -euo pipefail

# ── 颜色 ──────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}▶${NC} $*"; }
success() { echo -e "${GREEN}✓${NC} $*"; }
warn()    { echo -e "${YELLOW}⚠${NC} $*"; }
error()   { echo -e "${RED}✗${NC} $*" >&2; }
title()   { echo -e "\n${BOLD}${BLUE}$*${NC}"; echo -e "${BLUE}$(printf '%.0s─' {1..50})${NC}"; }

# ── 检测模式 ──────────────────────────────────────────────────
MODE="full"  # full | start | config
for arg in "$@"; do
  case "$arg" in
    --start)  MODE="start"  ;;
    --config) MODE="config" ;;
  esac
done

# ── 脚本目录（即项目根目录）──────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── 欢迎语 ────────────────────────────────────────────────────
clear
echo -e "${BOLD}"
echo "  ██╗     ██╗     ███╗   ███╗    ██╗  ██╗██████╗ "
echo "  ██║     ██║     ████╗ ████║    ██║ ██╔╝██╔══██╗"
echo "  ██║     ██║     ██╔████╔██║    █████╔╝ ██████╔╝"
echo "  ██║     ██║     ██║╚██╔╝██║    ██╔═██╗ ██╔══██╗"
echo "  ███████╗███████╗██║ ╚═╝ ██║    ██║  ██╗██████╔╝"
echo "  ╚══════╝╚══════╝╚═╝     ╚═╝    ╚═╝  ╚═╝╚═════╝ "
echo -e "${NC}"
echo -e "  ${CYAN}LLM 知识库 — 一键部署脚本${NC}"
echo ""

# ══════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════

# 检测操作系统
detect_os() {
  if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "macos"
  elif [[ -f /etc/os-release ]]; then
    source /etc/os-release
    case "$ID" in
      ubuntu|debian|linuxmint|pop) echo "debian" ;;
      centos|rhel|fedora|rocky|almalinux) echo "rpm" ;;
      arch|manjaro|endeavouros) echo "arch" ;;
      *) echo "linux" ;;
    esac
  else
    echo "linux"
  fi
}

OS=$(detect_os)
success "检测到系统：$OS"

# 读取带默认值的输入
prompt_input() {
  local label="$1" default="$2" var_name="$3" secret="${4:-}"
  if [[ -n "$secret" ]]; then
    printf "  ${BOLD}%s${NC}" "$label"
    [[ -n "$default" ]] && printf " ${CYAN}[默认: %s]${NC}" "$default"
    printf ": "
    read -rs value
    echo ""
  else
    printf "  ${BOLD}%s${NC}" "$label"
    [[ -n "$default" ]] && printf " ${CYAN}[默认: %s]${NC}" "$default"
    printf ": "
    read -r value
  fi
  value="${value:-$default}"
  eval "$var_name='$value'"
}

# 选择菜单
prompt_choice() {
  local label="$1" default="$2" var_name="$3"
  shift 3
  local options=("$@")
  echo -e "  ${BOLD}$label${NC}"
  for i in "${!options[@]}"; do
    if [[ "$((i+1))" == "$default" ]]; then
      echo -e "    ${GREEN}[$((i+1))]${NC} ${options[$i]} ${CYAN}← 默认${NC}"
    else
      echo -e "    [${CYAN}$((i+1))${NC}] ${options[$i]}"
    fi
  done
  printf "  选择 [%s]: " "$default"
  read -r choice
  choice="${choice:-$default}"
  local idx=$((choice - 1))
  if [[ $idx -ge 0 && $idx -lt ${#options[@]} ]]; then
    eval "$var_name='${options[$idx]}'"
  else
    eval "$var_name='${options[$((default-1))]}'"
  fi
}

# ══════════════════════════════════════════════════════════════
# 阶段 1：安装系统依赖
# ══════════════════════════════════════════════════════════════
install_deps() {
  title "📦 安装系统依赖"

  # ── Python ──────────────────────────────────────────────────
  PYTHON=""
  for py in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$py" &>/dev/null; then
      ver=$($py -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
      major=${ver%%.*}; minor=${ver#*.}
      if [[ $major -ge 3 && $minor -ge 10 ]]; then
        PYTHON="$py"; break
      fi
    fi
  done

  if [[ -z "$PYTHON" ]]; then
    warn "未找到 Python 3.10+，开始安装..."
    case "$OS" in
      macos)
        if ! command -v brew &>/dev/null; then
          info "安装 Homebrew..."
          /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
          eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv)"
        fi
        brew install python@3.11
        PYTHON="python3.11"
        ;;
      debian)
        sudo apt-get update -qq
        sudo apt-get install -y python3.11 python3.11-venv python3-pip
        PYTHON="python3.11"
        ;;
      rpm)
        sudo dnf install -y python3.11 python3.11-pip || \
        sudo yum install -y python3.11 python3-pip
        PYTHON="python3.11"
        ;;
      arch)
        sudo pacman -Sy --noconfirm python
        PYTHON="python3"
        ;;
      *)
        error "无法自动安装 Python，请手动安装 Python 3.10+"
        exit 1
        ;;
    esac
  fi
  success "Python: $($PYTHON --version)"

  # ── venv（Debian/Ubuntu 需要单独安装）──────────────────────
  if [[ "$OS" == "debian" ]] && ! $PYTHON -m venv --help &>/dev/null 2>&1; then
    info "安装 python3-venv..."
    PYVER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    sudo apt-get install -y "python${PYVER}-venv" 2>/dev/null || \
    sudo apt-get install -y python3-venv
  fi

  # ── pip ─────────────────────────────────────────────────────
  if ! $PYTHON -m pip --version &>/dev/null; then
    case "$OS" in
      macos)   brew install python@3.11 ;;
      debian)  sudo apt-get install -y python3-pip ;;
      rpm)     sudo dnf install -y python3-pip ;;
      arch)    sudo pacman -Sy --noconfirm python-pip ;;
    esac
  fi
  success "pip: $($PYTHON -m pip --version | awk '{print $2}')"

  # ── git（可选，用于 wiki 版本快照）──────────────────────────
  if ! command -v git &>/dev/null; then
    info "安装 git..."
    case "$OS" in
      macos)   brew install git ;;
      debian)  sudo apt-get install -y git ;;
      rpm)     sudo dnf install -y git ;;
      arch)    sudo pacman -Sy --noconfirm git ;;
    esac
  fi
  success "git: $(git --version | awk '{print $3}')"
}

# ══════════════════════════════════════════════════════════════
# 阶段 2：安装 Python 依赖
# ══════════════════════════════════════════════════════════════
install_python_deps() {
  title "🐍 安装 Python 依赖"

  # 创建虚拟环境
  if [[ ! -d ".venv" ]]; then
    info "创建虚拟环境 .venv ..."
    $PYTHON -m venv .venv
  fi
  source .venv/bin/activate
  PYTHON=".venv/bin/python3"
  success "虚拟环境已激活"

  info "安装核心依赖..."
  pip install -q --upgrade pip
  pip install -q -r requirements.txt
  success "核心依赖安装完成"

  info "安装 Web 服务依赖..."
  pip install -q -r web/requirements.txt
  success "Web 依赖安装完成"

  # 可选依赖
  echo ""
  echo -e "  ${BOLD}可选功能：${NC}"

  read -rp "  安装 PDF 支持？(PyMuPDF) [Y/n]: " install_pdf
  if [[ "${install_pdf,,}" != "n" ]]; then
    pip install -q pymupdf && success "PDF 支持已安装" || warn "PDF 安装失败（可跳过）"
  fi

  read -rp "  安装 YouTube 字幕提取？(yt-dlp) [Y/n]: " install_ytdlp
  if [[ "${install_ytdlp,,}" != "n" ]]; then
    pip install -q yt-dlp && success "yt-dlp 已安装" || warn "yt-dlp 安装失败（可跳过）"
  fi
}

# ══════════════════════════════════════════════════════════════
# 阶段 3：交互式配置
# ══════════════════════════════════════════════════════════════
run_config() {
  title "⚙️  配置知识库"

  # 读取现有配置
  existing_key=""
  existing_base_url=""
  existing_model=""
  existing_budget=""
  if command -v python3 &>/dev/null && [[ -f "config.yaml" ]]; then
    existing_key=$(python3 -c "import yaml; c=yaml.safe_load(open('config.yaml')); print(c.get('api_key',''))" 2>/dev/null || echo "")
    existing_base_url=$(python3 -c "import yaml; c=yaml.safe_load(open('config.yaml')); print(c.get('base_url',''))" 2>/dev/null || echo "")
    existing_model=$(python3 -c "import yaml; c=yaml.safe_load(open('config.yaml')); print(c.get('llm',{}).get('model',''))" 2>/dev/null || echo "")
    existing_budget=$(python3 -c "import yaml; c=yaml.safe_load(open('config.yaml')); print(c.get('compile',{}).get('budget_limit_usd',5.0))" 2>/dev/null || echo "5.0")
  fi

  echo ""
  echo -e "  ${YELLOW}请依次填写配置项，直接回车使用默认值${NC}"
  echo ""

  # ── API Key ──────────────────────────────────────────────────
  echo -e "  ${BOLD}1. Anthropic API Key${NC}"
  echo -e "     获取地址：https://console.anthropic.com → API Keys"
  if [[ -n "$existing_key" ]]; then
    echo -e "     ${CYAN}当前已配置，直接回车保留${NC}"
    printf "  API Key [已配置，回车保留]: "
    read -rs NEW_API_KEY
    echo ""
    NEW_API_KEY="${NEW_API_KEY:-$existing_key}"
  else
    printf "  API Key (sk-ant-...): "
    read -rs NEW_API_KEY
    echo ""
    while [[ -z "$NEW_API_KEY" ]]; do
      warn "API Key 不能为空"
      printf "  API Key: "
      read -rs NEW_API_KEY
      echo ""
    done
  fi
  success "API Key 已设置"

  # ── Base URL（中转）──────────────────────────────────────────
  echo ""
  echo -e "  ${BOLD}2. API 中转地址（可选）${NC}"
  echo -e "     使用 Anthropic 官方 API 直接留空回车"
  echo -e "     使用中转服务则填地址，如 https://api.anyruter.com"
  prompt_input "Base URL" "${existing_base_url}" NEW_BASE_URL
  if [[ -z "$NEW_BASE_URL" ]]; then
    success "使用官方 Anthropic API"
  else
    success "使用中转地址：$NEW_BASE_URL"
  fi

  # ── 模型选择 ─────────────────────────────────────────────────
  echo ""
  echo -e "  ${BOLD}3. 默认模型（复杂任务：编译/问答/报告）${NC}"
  prompt_choice "选择模型" "1" NEW_MODEL \
    "claude-sonnet-4-6   (推荐，质量/成本平衡)" \
    "claude-opus-4-6     (最强，成本最高)" \
    "claude-haiku-4-5-20251001 (最快最便宜，质量较低)"
  # 提取模型 ID（去掉注释）
  NEW_MODEL=$(echo "$NEW_MODEL" | awk '{print $1}')
  success "默认模型：$NEW_MODEL"

  # ── 预算上限 ─────────────────────────────────────────────────
  echo ""
  echo -e "  ${BOLD}4. 单次编译预算上限（USD）${NC}"
  echo -e "     超出此金额自动停止编译，防止意外超支"
  prompt_input "预算上限 USD" "${existing_budget:-5.0}" NEW_BUDGET
  # 验证为数字
  if ! [[ "$NEW_BUDGET" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
    warn "格式不对，使用默认值 5.0"
    NEW_BUDGET="5.0"
  fi
  success "预算上限：\$$NEW_BUDGET"

  # ── Wiki 语言 ────────────────────────────────────────────────
  echo ""
  echo -e "  ${BOLD}5. 知识库语言${NC}"
  prompt_choice "选择语言" "1" NEW_LANG \
    "zh（中文）" \
    "en（英文）" \
    "ja（日文）"
  NEW_LANG=$(echo "$NEW_LANG" | awk '{print $1}')
  success "语言：$NEW_LANG"

  # ── Web 端口 ─────────────────────────────────────────────────
  echo ""
  echo -e "  ${BOLD}6. Web 服务端口${NC}"
  prompt_input "端口号" "8000" NEW_PORT
  if ! [[ "$NEW_PORT" =~ ^[0-9]+$ ]]; then
    warn "格式不对，使用默认值 8000"
    NEW_PORT="8000"
  fi
  success "端口：$NEW_PORT"

  # ── 写入 config.yaml ─────────────────────────────────────────
  echo ""
  info "写入 config.yaml..."

  python3 - <<PYEOF
import yaml

try:
    with open("config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
except FileNotFoundError:
    cfg = {}

cfg["api_key"]  = """$NEW_API_KEY"""
cfg["base_url"] = """$NEW_BASE_URL"""

cfg.setdefault("llm", {})["model"] = "$NEW_MODEL"
cfg.setdefault("compile", {})["budget_limit_usd"] = float("$NEW_BUDGET")
cfg.setdefault("wiki", {})["language"] = "$NEW_LANG"

with open("config.yaml", "w", encoding="utf-8") as f:
    yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print("  ✓ config.yaml 已更新")
PYEOF

  # 保存端口供启动使用
  echo "$NEW_PORT" > .install_port
  success "配置写入完成"
}

# ══════════════════════════════════════════════════════════════
# 阶段 4：初始化项目结构
# ══════════════════════════════════════════════════════════════
init_project() {
  title "📁 初始化项目目录"
  mkdir -p raw/articles raw/papers raw/media-notes raw/repos
  mkdir -p wiki/answers wiki/slides
  mkdir -p .state templates
  success "目录结构已就绪"

  if [[ ! -f ".gitignore" ]]; then
    cat > .gitignore <<'EOF'
.venv/
__pycache__/
*.pyc
.DS_Store
*.egg-info/
.env
EOF
    success ".gitignore 已创建"
  fi

  if command -v git &>/dev/null && [[ ! -d ".git" ]]; then
    git init -q && git add -A && git commit -q -m "init: 初始化知识库" 2>/dev/null || true
    success "git 仓库已初始化"
  fi
}

# ══════════════════════════════════════════════════════════════
# 阶段 5：测试 API 连通性
# ══════════════════════════════════════════════════════════════
test_api() {
  title "🔌 测试 API 连通性"
  info "发送测试请求（约 3-10 秒）..."

  if .venv/bin/python3 -c "
import sys; sys.path.insert(0, '.')
import yaml
cfg = yaml.safe_load(open('config.yaml').read())
from tools.llm_client import LLMClient
c = LLMClient(cfg)
r = c.call('Reply with the single word: OK', max_tokens=5)
print(f'  响应：{r.strip()}')
print(f'  模型：{cfg.get(\"llm\",{}).get(\"model\",\"\")}')
" 2>&1; then
    success "API 连通正常 🎉"
  else
    warn "API 测试失败，请检查 API Key 和 Base URL"
    echo -e "  可运行 ${CYAN}make test-api${NC} 重新测试"
  fi
}

# ══════════════════════════════════════════════════════════════
# 阶段 6：启动 Web 服务
# ══════════════════════════════════════════════════════════════
start_web() {
  title "🚀 启动 Web 服务"

  PORT="${NEW_PORT:-8000}"
  if [[ -f ".install_port" ]]; then
    PORT=$(cat .install_port)
  fi

  # 检查端口占用
  if lsof -i ":$PORT" &>/dev/null 2>&1; then
    warn "端口 $PORT 已被占用，尝试使用 $((PORT+1))..."
    PORT=$((PORT + 1))
  fi

  # 激活虚拟环境
  if [[ -f ".venv/bin/activate" ]]; then
    source .venv/bin/activate
  fi

  echo ""
  echo -e "  ${GREEN}${BOLD}知识库 Web 界面启动中...${NC}"
  echo ""
  echo -e "  访问地址：${BOLD}${CYAN}http://localhost:${PORT}${NC}"
  echo -e "  停止服务：${BOLD}Ctrl + C${NC}"
  echo ""
  echo -e "  ${YELLOW}首次访问如已配置 API Key，可直接开始使用${NC}"
  echo ""

  # 延迟后自动打开浏览器
  (sleep 2 && \
    if [[ "$OS" == "macos" ]]; then
      open "http://localhost:${PORT}"
    elif command -v xdg-open &>/dev/null; then
      xdg-open "http://localhost:${PORT}" 2>/dev/null
    fi
  ) &

  # 启动服务（前台）
  exec .venv/bin/uvicorn web.app:app --host 0.0.0.0 --port "$PORT"
}

# ══════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════
main() {
  case "$MODE" in
    full)
      install_deps
      install_python_deps
      run_config
      init_project
      test_api
      echo ""
      echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
      echo -e "${GREEN}${BOLD}  ✓ 安装完成！即将启动 Web 界面...${NC}"
      echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
      sleep 1
      start_web
      ;;
    config)
      # 仅重新配置
      if [[ -f ".venv/bin/python3" ]]; then
        PYTHON=".venv/bin/python3"
      fi
      run_config
      test_api
      echo -e "\n  重新启动：${CYAN}bash install.sh --start${NC}"
      ;;
    start)
      # 仅启动
      if [[ ! -f ".venv/bin/uvicorn" ]]; then
        error "未找到虚拟环境，请先运行：bash install.sh"
        exit 1
      fi
      start_web
      ;;
  esac
}

main
