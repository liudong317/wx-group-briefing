# Windows 微信群日报完整教程

完成这份教程后，Windows 会每天自动读取指定微信群当天的聊天，生成 Markdown 和 1–2 页 PDF 日报。

## 准备条件

- Windows 10 或 Windows 11，推荐 x64；
- 已安装并登录微信 4.x，任务管理器中能看到 `Weixin.exe`；
- 有权读取和总结目标群聊；
- 可以使用 PowerShell，初始化时可以“以管理员身份运行”。

## 第 1 步：安装基础工具

打开 PowerShell，安装 `uv`：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

关闭并重新打开 PowerShell，确认：

```powershell
uv --version
git --version
```

如果没有 Git，请从 <https://git-scm.com/download/win> 安装 Git for Windows，然后重新打开 PowerShell。

## 第 2 步：下载项目

```powershell
git clone https://github.com/Leobai03/wechat-group-daily.git
Set-Location wechat-group-daily
uv sync
Copy-Item config.example.toml config.toml
```

## 第 3 步：创建并保存薛定Token API Key

先按[薛定Token API Key 教程](薛定Token接入教程.md)完成注册和创建。

项目已经内置：

```text
模型名：claude-opus-4-8
Base URL：https://xuedingtoken1.com/v1
```

在项目目录保存 API Key：

```powershell
uv run wechat-daily set-api-key
```

密钥会进入当前 Windows 用户的凭据管理器，不会写进 `config.toml`。

## 第 4 步：填写群名

用记事本打开配置：

```powershell
notepad config.toml
```

填写一个或多个群：

```toml
[wechat]
groups = ["产品交流群", "AI 创业群"]
```

保存并关闭记事本。群名必须与微信中完全一致。

## 第 5 步：初始化微信本地数据库

保持微信打开并处于登录状态。在开始菜单搜索“PowerShell”，右键选择“以管理员身份运行”，再进入项目目录。

例如项目在下载目录：

```powershell
Set-Location "$HOME\Downloads\wechat-group-daily"
```

执行：

```powershell
.\.venv\Scripts\wechat-cli.exe init
```

`wechat-cli` 会自动寻找 Windows 微信数据目录，读取 `Weixin.exe` 进程内存并提取数据库密钥。如果检测到多个微信账号，选择当前正在使用的账号。

初始化成功后，配置位于：

```text
%USERPROFILE%\.wechat-cli\
```

不要公开 `all_keys.json`，也不要把完整初始化终端截图上传到 GitHub或社交平台。

## 第 6 步：检查并确认群名

回到普通 PowerShell，在项目目录执行：

```powershell
uv run wechat-daily doctor
```

“数据库密钥”“目标群”和“AI 总结”都通过后继续。

列出最近出现的微信群：

```powershell
uv run wechat-daily groups
```

如果之前填错，把输出中的准确群名复制到 `config.toml`。

## 第 7 步：先只读测试

```powershell
uv run wechat-daily run --dry-run --date today
```

这一步只读取和脱敏，不调用 AI，也不写日报。确认消息数量正常后再继续。

## 第 8 步：生成真实日报

```powershell
uv run wechat-daily run --date today
```

输出位于：

```text
reports\日期_群名_微信群日报.md
reports\日期_群名_微信群日报.pdf
```

生成昨天的日报：

```powershell
uv run wechat-daily run --date yesterday
```

临时指定多个群：

```powershell
uv run wechat-daily run --date today `
  --group "产品交流群" `
  --group "AI 创业群"
```

把已有 Markdown 转换为 PDF：

```powershell
uv run wechat-daily render-pdf "reports\某份日报.md"
```

PDF 会优先使用 Windows 自带的微软雅黑或黑体显示中文。

## 第 9 步：每天自动运行

```powershell
uv run wechat-daily install-schedule
```

程序会通过 Windows 任务计划程序创建每天 22:00 的任务。确认任务：

```powershell
Get-ScheduledTask -TaskName "com.local.wechat-group-daily"
```

手动触发一次任务：

```powershell
Start-ScheduledTask -TaskName "com.local.wechat-group-daily"
```

定时运行副本、日报和日志位于：

```text
%LOCALAPPDATA%\com.local.wechat-group-daily\
%LOCALAPPDATA%\com.local.wechat-group-daily\reports\
%LOCALAPPDATA%\com.local.wechat-group-daily\logs\
```

每天执行时，Windows 用户需要处于登录状态、微信正在运行且网络可用。

修改运行时间：

```toml
[schedule]
label = "com.local.wechat-group-daily"
hour = 21
minute = 30
```

修改配置或更新代码后，重新执行 `uv run wechat-daily install-schedule`。

## 更新项目

```powershell
git pull
uv sync
uv run wechat-daily install-schedule
```

## Windows 常见报错

### `Weixin.exe 未运行`

打开并登录微信，在任务管理器“详细信息”中确认存在 `Weixin.exe`。

### 无法打开进程或读取内存

关闭当前窗口，右键 PowerShell选择“以管理员身份运行”，重新进入项目目录并执行：

```powershell
.\.venv\Scripts\wechat-cli.exe init --force
```

### 未自动找到微信数据目录

先确认 Windows 微信已经产生本地聊天记录。也可以按 `wechat-cli` 的报错提示，用 `--db-dir` 指定实际的 `db_storage` 目录。

### 找不到群

运行 `uv run wechat-daily groups`，复制准确群名。

### 任务计划存在但没有日报

确认触发时 Windows 用户已登录、微信正在运行，然后检查：

```text
%LOCALAPPDATA%\com.local.wechat-group-daily\logs\scheduler.out.log
%LOCALAPPDATA%\com.local.wechat-group-daily\logs\scheduler.err.log
```

也可以在“任务计划程序”中查看任务的“上次运行结果”。

### 微信升级后读取失败

以管理员身份重新执行 `wechat-cli.exe init --force`，然后先跑一次 dry-run。

### AI 请求失败

参照[薛定Token API Key 教程的常见问题](薛定Token接入教程.md#常见问题)。

## 隐私提醒

程序只读访问本地数据库，但脱敏后的聊天会发送给薛定Token及其上游模型。自动脱敏不能识别所有秘密；没有授权或包含机密信息的群不要使用。
