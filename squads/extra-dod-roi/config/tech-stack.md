# Tech stack — extra-dod-roi

| Layer | Tech |
|-------|------|
| Orchestration | AIOX 5.3.0 squad task-first |
| Workers | Python 3 stdlib (+ PyYAML if available) |
| Product (context) | Python crawlers, PostgreSQL, Makefile, GitHub Actions |
| Validation | Node squad-validator / squad-analyzer from `.aiox-core` |
| VCS | git + gh CLI |

Out of scope for this squad to introduce: K8s, Kafka, Redis, Elasticsearch, multi-tenant auth, billing.
