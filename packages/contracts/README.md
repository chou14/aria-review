# contracts

## 共享契约 fixtures

`packages/contracts/fixtures/*.json` 是前后端共享的契约样例，单一生成入口：

```bash
cd services/agent
.venv/bin/python scripts/gen_contract_fixtures.py
```

后端 schema 或响应字段变更后：

1. 修改后端 schema / 实现。
2. 运行生成命令，更新 `packages/contracts/fixtures/*.json`。
3. 前端 dev/e2e/组件测试直接消费这些 JSON，不再维护手写副本。
4. 运行后端契约测试与前端 `typecheck` / `test`。
