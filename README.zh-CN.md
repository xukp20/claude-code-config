# claude-code-config

我的 Claude Code 状态栏与 compact 配置。[English](README.md)

文件:

- `statusline.py` — 状态栏脚本(Python 3,仅标准库)。
- `settings.example.json` — `~/.claude/settings.json` 中相关的部分。

## 安装

```bash
cp statusline.py ~/.claude/statusline.py
# 再把 settings.example.json 合并进 ~/.claude/settings.json
```

基于 Claude Code 2.1.318–2.1.319 开发。脚本读取 Claude Code 通过 stdin 传给状态栏命令的 JSON,输出一行文本;出错时退回只显示当前目录。

## 状态栏含义

```
/path/to/project │ Opus 5.5 high │ ctx 142k/300k +8.2k ic:100k │ cache 97% warm 54m ic 3m │ 5h 31% 2h10m · 7d 12% 5d3h
```

| 段 | 含义 |
|---|---|
| 工作目录 | 会话启动目录(`project_dir`),Bash 里 `cd` 不会改变它。 |
| 模型 + effort | 显示名和当前 effort 等级。 |
| `ctx A/B` | 当前上下文 `A` 对比 **auto-compact 阈值** `B`(不是 1M 窗口)。<50% 绿,<80% 黄,其余红。`+N` 是上一次请求写入缓存的 token。 |
| `ic:100k` | idle compact 的触发门槛。灰色 = 上下文还不够;**绿色** = 已达到门槛;`ic:off` = 已关闭。 |
| `cache N%` | 上一次请求的 prompt cache 命中率。 |
| `TTL5m` | 缓存 TTL 只有 5 分钟(idle compact 需要 1h)。 |
| `warm 54m` | 距离缓存过期的时间。 |
| `ic 3m` | 距离 idle compact 触发的时间(仅在会触发时显示),`ic due` = 即将触发。 |
| `cmp` | 刚 compact 完,缓存前缀已失效,倒计时不再显示。 |
| `COLD next +Nk` | 缓存已过期,下一条消息要重新缓存 N token。 |
| `miss N` | 缓存未命中次数。 |
| `5h` / `7d` | 订阅限额用量与重置倒计时。 |
| `?` / `!` | 限额告警生效:某个窗口被判定接近上限时,Claude Code 会跳过 idle compact。`!` 标在该窗口上,`?` 标在 ic 倒计时上。 |

## Compact 配置

**auto-compact 阈值**(`ctx` 里 `/B` 的来源),优先级:

1. 环境变量 `CLAUDE_CODE_AUTO_COMPACT_WINDOW`(下限 100k)
2. `modelSettings["<model-id>"].autoCompactWindow`
3. 顶层 `autoCompactWindow`
4. 默认值:1M 窗口约 967k,否则等于窗口大小

我给 Opus 和 Sonnet 都设成 300k:上下文太长又慢又贵,宁可早点 compact。

**idle compact** — 2.1.318 的行为(观察所得,非官方文档):

- 需要 1h 的 prompt cache TTL;
- 需要上下文 ≥ `max(100k, CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS)`,默认 200k;
- 在最后一次请求后 TTL 的 90% 处触发(1h TTL 约 54 分钟);
- 限额状态不是 "allowed" 时会跳过。客户端按(已用比例,窗口已过比例)判断:
  - 5h 窗口:前 72% 的时间内已用 ≥ 90%;
  - 7d 窗口:前 60% 内已用 ≥ 75%,前 35% 内 ≥ 50%,或前 15% 内 ≥ 25%。

  服务端也可能标记窗口,状态栏看不到,所以没有 `?` 并不保证一定会 compact。

我把 `CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS` 降到 100k(下限),让较小的会话空闲时也会被 compact。状态栏读的是 Claude Code 传给它的环境变量,所以改完 settings 要等会话重新加载后才会反映。

## 按模型设置

`modelSettings` 还支持按模型设 `effortLevel`,示例里 Opus 设为 `high`。

刻意不包含:权限模式、沙箱开关等个人环境选择。
