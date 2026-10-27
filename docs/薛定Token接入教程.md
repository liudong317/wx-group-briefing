# 薛定Token注册、购买与 API Key 创建教程

这一页只解决一件事：拿到可用于微信群日报的薛定Token API Key，并安全保存到 Mac 或 Windows。

项目已经内置以下参数，不需要自己猜：

```text
模型名：claude-opus-4-8
Base URL：https://xuedingtoken1.com/v1
```

## 第 1 步：注册或登录

打开[薛定Token主站](https://xuedingtoken1.com/)，完成注册或登录。

如需购买额度，可以使用[购买额度（邀请链接）](https://shop.xuedingtoken.com/?invite=XLPB9REJ)。购买链接包含邀请码，链接提供者可能获得推广权益。

薛定Token是第三方服务，与本项目、OpenAI、Anthropic、腾讯或微信不存在官方隶属关系。不要把充值理解为收益产品，也不要购买超过自己实际使用需求的额度。

## 第 2 步：进入令牌管理

登录薛定Token后台后：

1. 在左侧菜单寻找“令牌”“API Key”或“令牌管理”；
2. 点击“创建令牌”“添加令牌”或“创建新的 API Key”；
3. 如果后台界面名称略有变化，选择用于创建 API 调用密钥的页面，不要复制登录密码或邀请码。

## 第 3 步：填写令牌信息

建议这样填写：

| 项目 | 建议值 |
| --- | --- |
| 名称 | `wechat-group-daily` |
| 额度 | 首次测试先设置小额度，跑通后再按需要调整 |
| 有效期 | 按你的实际使用周期设置 |
| 模型权限 | 确认允许调用 `claude-opus-4-8` |
| IP 或来源限制 | 熟悉固定出口 IP 时再设置；不确定可先按后台默认值测试 |

点击创建后立即复制完整 API Key。有些后台只显示一次，关闭弹窗后可能无法再次查看，只能重新生成。

## 第 4 步：把 API Key 保存到系统凭据库

进入已经下载好的 `wechat-group-daily` 项目目录，执行：

```bash
uv run wechat-daily set-api-key
```

根据提示粘贴两遍 API Key。输入不会显示：

- macOS：保存到当前用户的“钥匙串访问”；
- Windows：保存到当前用户的“凭据管理器”。

不要把 API Key 写进 `config.toml`、代码、Issue、聊天截图或 Git 提交。

## 第 5 步：确认配置

`config.toml` 中应保留：

```toml
[ai]
provider = "openai-compatible"
base_url = "https://xuedingtoken1.com/v1"
model = "claude-opus-4-8"
api_key_env = "WECHAT_DAILY_API_KEY"
api_key_service = "wechat-group-daily-xuedingtoken"
api_key_account = ""
command_timeout_seconds = 600
```

然后运行：

```bash
uv run wechat-daily doctor
```

`doctor` 显示“密钥可读取”，说明本机已经能找到 API Key。它不会发送真实聊天；真正的接口、余额和模型权限要通过一次正式运行验证：

```bash
uv run wechat-daily run --date today
```

## 常见问题

### 找不到 API Key

确认你是在当前项目目录执行 `uv run wechat-daily set-api-key`，并且保存密钥与运行日报使用的是同一个系统账号。

### HTTP 401

通常是 API Key 错误、已失效或复制不完整。重新创建 Key，再运行 `set-api-key` 覆盖旧值。

### HTTP 403

检查令牌的模型权限、账号权限和有效期。

### HTTP 404

确认 Base URL 是 `https://xuedingtoken1.com/v1`，不要填写主站首页。

### 模型不存在

确认模型名完整填写为 `claude-opus-4-8`。如果后台将来调整模型标识，应以当时后台模型列表为准。

### 余额不足

根据实际需要购买额度。不要在 Issue 或公开截图中展示订单、余额、API Key或个人账号信息。

## 密钥泄露或不再使用

立即到薛定Token后台撤销旧 Key，再创建新 Key并重新执行：

```bash
uv run wechat-daily set-api-key
```

接下来选择你的系统教程：

- [macOS 完整教程](macOS使用教程.md)
- [Windows 完整教程](Windows使用教程.md)
