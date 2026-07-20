This guide uses [`llmdbenchmark`](https://github.com/llm-d/llm-d-benchmark) —
the supported standard CLI for llm-d performance benchmarking. The CLI
automatically deploys a harness pod (`llmdbench-harness-launcher`) into your
namespace to drive the workload (the `HARNESS` and `WORKLOAD` set in the
environment section), collect the results, and tear itself down when
finished.

> [!IMPORTANT]
> A more in-depth explanation and features for benchmarking llm-d guides can
> be found at [`helpers/benchmark.md`](../../helpers/benchmark.md) — start
> there when something goes wrong. For even more details see
> [`llm-d-benchmark` on GitHub](https://github.com/llm-d/llm-d-benchmark).

### 1. Install the CLI

Automatically clone the benchmark repository into `./llm-d-benchmark/` and
create a virtualenv at `./llm-d-benchmark/.venv/` containing dependencies:

<!-- step -->
```bash
curl -sSL https://raw.githubusercontent.com/llm-d/llm-d-benchmark/${BENCHMARK_REF}/install.sh | bash
```

<!-- step -->
```bash
cd llm-d-benchmark
source .venv/bin/activate
llmdbenchmark --version
```

> [!NOTE]
> Subsequent `llmdbenchmark` commands assume you are inside the
> `llm-d-benchmark` repo directory with the `venv` activated. If you open a
> new shell, re-run the commands above.

### 2. Resolve the endpoint of the stack you just deployed

Get the proxy IP, then set the endpoint URL and the gateway class (which
tells the CLI which deployment topology the cluster is actually running):

<!-- import get-router-ip.md -->

<!-- step dry-run=skip -->
```bash
export ENDPOINT_URL="http://${IP}"
```

<!-- when router_mode=standalone -->
<!-- step -->
```bash
export GATEWAY_CLASS="epponly"
```
<!-- end -->
<!-- when router_mode=gateway -->
Match the provider you used when deploying the gateway:

<!-- step -->
```bash
export GATEWAY_CLASS="${PROVIDER_NAME}"
```
<!-- end -->

### 3. Run the benchmark profile

Benchmark results are copied to the `workspace` directory on the machine
running the CLI; by default the CLI auto-generates a timestamped workspace and
prints its full path in the logs. Pass `--workspace <DIR>` (before the `run`
subcommand) to choose where results land.

<!-- step dry-run=skip -->
```bash
llmdbenchmark \
  --spec           guides/${GUIDE_NAME} \
  run \
  --endpoint-url   "${ENDPOINT_URL}" \
  --gateway-class  "${GATEWAY_CLASS}" \
  --model          "${MODEL}" \
  --namespace      "${NAMESPACE}" \
  --harness        "${HARNESS}" \
  --workload       "${WORKLOAD}" \
  --analyze
```

> [!NOTE]
> Depending on your cluster you may need to extend the default timeout values;
> `bind`, `access` and `wait-timeout` times of PVCs and pods can be arbitrarily
> slower on some systems — see `llmdbenchmark run --help` for the knobs.
