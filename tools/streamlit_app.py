"""Lightweight Streamlit dashboard for local artifacts."""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

ARTIFACTS = Path(".artifacts")


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def main() -> None:
    st.set_page_config(page_title="Auto-Develope Dashboard", layout="wide")
    st.title("Auto-Develope 本地运行监控")

    st.sidebar.header("Artifacts 配置")
    artifacts_root = st.sidebar.text_input("Artifacts 路径", str(ARTIFACTS))
    root = Path(artifacts_root).expanduser().resolve()

    st.sidebar.write("点击下方按钮手动刷新数据")
    if st.sidebar.button("刷新", type="primary"):
        st.experimental_rerun()

    map_elites = _load_json(root / "map_elites.json")
    prompt_telemetry = _load_json(root / "prompt_telemetry.json")
    run_state = _load_json(root / "run_state.json")

    st.subheader("提示臂状态")
    if prompt_telemetry and "arms" in prompt_telemetry:
        import pandas as pd

        arms_df = pd.DataFrame.from_dict(prompt_telemetry["arms"], orient="index")
        st.dataframe(arms_df.reset_index(names="arm"))
        st.caption("包含成功率 proxy (successes/failures 参数)、recent_reward、invalid_responses 与 linUCB 相关指标。")
    else:
        st.info("未找到 prompt_telemetry.json 或内容为空")

    st.subheader("linUCB 参数")
    if prompt_telemetry and "bandit" in prompt_telemetry:
        st.json(prompt_telemetry["bandit"], expanded=False)
    else:
        st.info("当前遥测未导出 bandit 附加参数")

    st.subheader("MAP-Elites 快照")
    if map_elites:
        pareto = map_elites.get("state", {}).get("pareto_front", [])
        st.write(f"Pareto 前沿候选数：{len(pareto)}")
        st.json(map_elites.get("state", {}).get("map_elites_cells", {}), expanded=False)
    else:
        st.info("未找到 map_elites.json")

    st.subheader("RunState 待评估队列")
    if run_state:
        pending = run_state.get("pending_candidates", [])
        st.write(f"待评估队列长度：{len(pending)}")
        if pending:
            ids = [item.get("id") for item in pending]
            st.write(ids[:20])
    else:
        st.info("未找到 run_state.json")

    st.subheader("Few-shot 案例库")
    fewshot_root = root / "fewshot"
    if fewshot_root.exists():
        problems = sorted(p.stem for p in fewshot_root.glob("*.jsonl"))
        if problems:
            problem = st.selectbox("选择问题", problems)
            lines = (fewshot_root / f"{problem}.jsonl").read_text(encoding="utf-8").splitlines()
            max_lines = st.slider("查看条数", 1, min(50, len(lines)), value=min(10, len(lines)))
            for line in lines[-max_lines:]:
                st.json(json.loads(line), expanded=False)
        else:
            st.info("Few-shot 目录暂无样例")
    else:
        st.info("未找到 fewshot 目录")

    st.subheader("候选样本代码预览")
    candidates_root = root / "candidates"
    if candidates_root.exists():
        problem_dirs = sorted(p.name for p in candidates_root.iterdir() if p.is_dir())
        if problem_dirs:
            problem = st.selectbox("选择问题仓", problem_dirs, key="candidate_problem")
            latest = sorted((candidates_root / problem).iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            if latest:
                candidate_dir = latest[0]
                st.write(f"最新候选：{candidate_dir.name}")
                for py_file in candidate_dir.glob("*.py"):
                    st.code(py_file.read_text(encoding="utf-8"), language="python")
            else:
                st.info("该问题暂无候选产出")
        else:
            st.info("候选目录为空")
    else:
        st.info("未找到 candidates 目录")

    st.caption("运行示例：`streamlit run tools/streamlit_app.py`，请提前 \`pip install streamlit\`")


+if __name__ == "__main__":
+    main()
+
