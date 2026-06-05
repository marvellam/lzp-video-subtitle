# 示例输出

这个目录展示一次短样片运行后的标准输出形态。

```text
final.srt
final.txt
review_focus.csv
```

说明：

- 示例来自本地测试片段，仅用于展示文件结构与字段格式。
- 普通用户优先检查 `final.srt` 和 `review_focus.csv`。
- debug 文件不放在输出根目录；正式运行时调试信息会进入 `debug/`。

## review_focus.csv 当前字段

```csv
idx,start,end,duration,text,risk,reason
```

常见 reason：

```text
short_duration
corrections:错误词->正确词
too_long
latin_leftover
```
