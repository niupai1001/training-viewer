# 用户状态存储

- 中文名：用户状态库
- 代码名：`UserStateStore`
- 位置：`src/training_viewer/user_state.py`
- 文件：`<数据目录>/user_state.sqlite3`

## 职责

保存**不可重建**的用户数据：

- 日志根目录（`watched_roots`）；
- Run 备注（`run_annotations.note`）；
- 收藏（`favorite`）；
- 保存的对比视图（`saved_views`）。

指标索引在 `index.sqlite3`，可随时删除重建；两个文件分离，删除索引不会清空备注/收藏/视图。

## 迁移

启动时 `migrate_from_index()` 读取旧 `index.sqlite3` 中的 `watched_roots`、`run_annotations`、`saved_views`，复制到独立库；旧表保留但不再作为权威。`saved_views`/根目录只在新库为空时复制，避免重复。

## 查询方式

`IndexDatabase` 在连接上执行 `ATTACH DATABASE ... AS user_state`；`IndexQueries` 使用 `user_state.watched_roots` / `user_state.run_annotations` / `user_state.saved_views`。删除 `index.sqlite3` 后重新创建索引，仍能连接同一个 user_state 文件。

## 测试

`tests/test_user_state.py`：删除索引后备注/收藏/视图仍存在；旧索引迁移一次。
