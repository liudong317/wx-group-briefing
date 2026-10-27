# macOS 微信群日报完整教程

完成这份教程后，Mac 会每天自动读取指定微信群当天的聊天，生成 Markdown 和 1–2 页 PDF 日报。

## 准备条件

- macOS，Apple Silicon 或 Intel；
- 已安装并登录微信 4.x；
- 有权读取和总结目标群聊；
- 可以使用终端并输入 Mac 登录密码。

## 第 1 步：安装基础工具

安装 `uv`：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

重新打开终端，确认：

```bash
uv --version
git --version
```

如果没有 Git，可先安装 Xcode Command Line Tools：

```bash
xcode-select --install
```

## 第 2 步：下载项目

```bash
git clone https://github.com/Leobai03/wechat-group-daily.git
cd wechat-group-daily
uv sync
cp config.example.toml config.toml
```

## 第 3 步：创建并保存薛定Token API Key

先按[薛定Token API Key 教程](薛定Token接入教程.md)完成注册和创建。

项目已经内置：

```text
模型名：claude-opus-4-8
Base URL：https://xuedingtoken1.com/v1
```

在项目目录保存 API Key：

```bash
uv run wechat-daily set-api-key
```

密钥会进入当前用户的 macOS 钥匙串，不会写进 `config.toml`。

## 第 4 步：填写群名

编辑 `config.toml`：

```toml
[wechat]
groups = ["产品交流群", "AI 创业群"]
```

群名必须与微信中完全一致。暂时不知道准确群名也没关系，初始化后可以用 `groups` 命令查。

## 第 5 步：给终端完全磁盘访问权限

打开：

```text
系统设置 → 隐私与安全性 → 完全磁盘访问权限
```

添加并启用你使用的终端，例如“终端”、iTerm2 或 IDE 内置终端。完成后完全退出终端并重新打开。

## 第 6 步：初始化微信本地数据库

保持微信打开并处于登录状态，先直接执行：

```bash
sudo ./.venv/bin/wechat-cli init
```

如果出现 `task_for_pid failed`，`wechat-cli` 会尝试提示重新签名。按照提示完全退出微信、完成签名、重新打开并登录，再次执行上面的 `init`。

自动处理失败时，可以在微信完全退出后手动添加内存读取所需的 entitlement：

```bash
sudo xattr -cr /Applications/WeChat.app
sudo codesign --force --sign - --entitlements /dev/stdin /Applications/WeChat.app <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.get-task-allow</key>
    <true/>
</dict>
</plist>
EOF
```

重新打开微信并登录，再运行 `sudo ./.venv/bin/wechat-cli init`。如果本机登录过多个微信账号，按提示选择当前正在使用的账号。初始化成功后，配置位于 `~/.wechat-cli/`。

> 重新签名可能让 macOS 再次询问截图、相机或麦克风权限，也可能影响微信自动更新。微信升级后通常要重新签名和 `init`。需要恢复官方签名时，从微信官方渠道重新安装。

## 第 7 步：检查并确认群名

```bash
uv run wechat-daily doctor
```

“数据库密钥”“目标群”和“AI 总结”都通过后继续。

列出最近出现的微信群：

```bash
uv run wechat-daily groups
```

如果之前填错群名，把输出中的准确名称复制到 `config.toml`。

## 第 8 步：先只读测试

```bash
uv run wechat-daily run --dry-run --date today
```

这一步只读取和脱敏，不调用 AI，也不写日报。确认消息数量正常后再继续。

## 第 9 步：生成真实日报

```bash
uv run wechat-daily run --date today
```

输出位于：

```text
reports/日期_群名_微信群日报.md
reports/日期_群名_微信群日报.pdf
```

生成昨天的日报：

```bash
uv run wechat-daily run --date yesterday
```

把已有 Markdown 单独转换为 PDF：

```bash
uv run wechat-daily render-pdf reports/某份日报.md
```

## 第 10 步：每天自动运行

```bash
uv run wechat-daily install-schedule
```

确认 `launchd` 已加载：

```bash
launchctl print gui/$(id -u)/com.local.wechat-group-daily
```

定时运行副本、日报和日志位于：

```text
~/Library/Application Support/com.local.wechat-group-daily/
~/Library/Application Support/com.local.wechat-group-daily/reports/
~/Library/Application Support/com.local.wechat-group-daily/logs/
```

每天执行时，Mac 需要处于登录状态、微信正在运行且网络可用。

修改运行时间：

```toml
[schedule]
label = "com.local.wechat-group-daily"
hour = 21
minute = 30
```

修改配置或更新代码后，重新执行 `uv run wechat-daily install-schedule`。

## 更新项目

```bash
git pull
uv sync
uv run wechat-daily install-schedule
```

## macOS 常见报错

### `task_for_pid failed`

确认终端已有完全磁盘访问权限，并按“第 6 步”给微信添加 `get-task-allow` entitlement，再使用 `sudo` 初始化。

### `Operation not permitted`

完全退出微信再签名；检查终端的“完全磁盘访问权限”和“App 管理”权限。

### 找不到群

运行 `uv run wechat-daily groups`，复制准确群名。

### 定时任务没有生成日报

确认执行时间 Mac 已登录且微信正在运行，再检查：

```text
~/Library/Application Support/com.local.wechat-group-daily/logs/
```

### 微信升级后读取失败

重新执行“第 6 步”的签名命令和 `sudo ./.venv/bin/wechat-cli init`。

### AI 请求失败

参照[薛定Token API Key 教程的常见问题](薛定Token接入教程.md#常见问题)。

## 隐私提醒

程序只读访问本地数据库，但脱敏后的聊天会发送给薛定Token及其上游模型。自动脱敏不能识别所有秘密；没有授权或包含机密信息的群不要使用。
