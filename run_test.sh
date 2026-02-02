#!/bin/bash
# AutoGLM 测试启动脚本
# 自动禁用代理并激活虚拟环境

# 保存原始代理设置
ORIGINAL_HTTP_PROXY="$http_proxy"
ORIGINAL_HTTPS_PROXY="$https_proxy"
ORIGINAL_ALL_PROXY="$all_proxy"

# 禁用代理
unset all_proxy
unset ALL_PROXY
unset http_proxy
unset HTTP_PROXY
unset https_proxy
unset HTTPS_PROXY

# 激活虚拟环境
source venv/bin/activate

# 运行测试
python src/api_test_runner.py "$@"

# 恢复代理设置
export http_proxy="$ORIGINAL_HTTP_PROXY"
export https_proxy="$ORIGINAL_HTTPS_PROXY"
export all_proxy="$ORIGINAL_ALL_PROXY"
