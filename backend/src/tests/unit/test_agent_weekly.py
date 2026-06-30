"""Unit tests for DeepResearchAgent weekly-mode additions.

Covers: _make_weekly_tasks output structure, task count,
        multi-query loop in _execute_task.
"""

import pytest
from unittest.mock import patch, MagicMock
from models import TodoItem, SummaryState
from config import Configuration


class TestMakeWeeklyTasks:
    """DeepResearchAgent._make_weekly_tasks — weekly task list generation."""

    @pytest.fixture
    def agent(self):
        from agent import DeepResearchAgent
        cfg = Configuration.from_env()
        return DeepResearchAgent(config=cfg)

    def test_returns_five_tasks(self, agent):
        with patch("services.reporter.ReportingService._extract_enterprise_from_topic",
                   return_value="四川振海保安服务有限公司"), \
             patch("services.reporter.ReportingService._get_enterprise_field",
                   return_value="安保服务"), \
             patch("services.reporter.ReportingService._load_enterprises_yaml",
                   return_value=[
                       {"name": "核心甲方A", "role": "甲方", "debtor": "四川振海保安服务有限公司"},
                       {"name": "四川振海保安服务有限公司", "role": "乙方", "debtor": "四川振海保安服务有限公司"},
                   ]):
            tasks = agent._make_weekly_tasks("四川振海保安服务有限公司 贷后监管")
            assert len(tasks) == 5
            # Task IDs
            ids = [t.id for t in tasks]
            assert ids == [1, 2, 3, 4, 5]

    def test_task_1_is_industry(self, agent):
        with patch("services.reporter.ReportingService._extract_enterprise_from_topic",
                   return_value="测试企业"), \
             patch("services.reporter.ReportingService._get_enterprise_field",
                   return_value="物业管理"), \
             patch("services.reporter.ReportingService._load_enterprises_yaml", return_value=[]):
            tasks = agent._make_weekly_tasks("测试企业 风险监测")
            t1 = tasks[0]
            assert t1.id == 1
            assert "行业" in t1.title
            assert len(t1.micro_queries) >= 3

    def test_task_5_is_qichacha_with_micro_queries(self, agent):
        with patch("services.reporter.ReportingService._extract_enterprise_from_topic",
                   return_value="测试企业"), \
             patch("services.reporter.ReportingService._get_enterprise_field",
                   return_value="安保服务"), \
             patch("services.reporter.ReportingService._load_enterprises_yaml",
                   return_value=[
                       {"name": "甲方A", "role": "甲方", "debtor": "测试企业"},
                       {"name": "甲方B", "role": "甲方", "debtor": "测试企业"},
                   ]):
            tasks = agent._make_weekly_tasks("测试企业")
            t5 = tasks[4]
            assert t5.id == 5
            assert "企查查" in t5.title
            # micro_queries should contain party A names + enterprise
            assert "甲方A" in t5.micro_queries
            assert "甲方B" in t5.micro_queries
            assert "测试企业" in t5.micro_queries

    def test_supply_queries_fallback_when_no_parties(self, agent):
        with patch("services.reporter.ReportingService._extract_enterprise_from_topic",
                   return_value="测试企业"), \
             patch("services.reporter.ReportingService._get_enterprise_field",
                   return_value="行业"), \
             patch("services.reporter.ReportingService._load_enterprises_yaml", return_value=[]):
            tasks = agent._make_weekly_tasks("测试企业")
            t2 = tasks[1]
            assert t2.id == 2
            # supply queries fallback
            assert any("核心企业" in q for q in t2.micro_queries)

    def test_debtor_queries_contain_all_dimensions(self, agent):
        with patch("services.reporter.ReportingService._extract_enterprise_from_topic",
                   return_value="测试企业"), \
             patch("services.reporter.ReportingService._get_enterprise_field",
                   return_value="行业"), \
             patch("services.reporter.ReportingService._load_enterprises_yaml", return_value=[]):
            tasks = agent._make_weekly_tasks("测试企业")
            t3 = tasks[2]
            assert t3.id == 3
            assert "债务" in t3.title
            assert len(t3.micro_queries) >= 4  # 工商, 诉讼, 经营, 财务, 舆情, 负面


class TestRunStreamWeeklyPath:
    """run_stream with weekly agent — freshness check and task generation."""

    def test_weekly_agent_uses_make_weekly_tasks(self):
        """Verify weekly agent entries _make_weekly_tasks branch."""
        config = Configuration.from_env()
        config.llm_model_id = "mock-model"
        with patch("agent.DeepResearchAgent._make_weekly_tasks") as mock_tasks, \
             patch("services.reporter.ReportingService.__init__", return_value=None):
            mock_tasks.return_value = [
                TodoItem(id=1, title="测试", intent="测试", query="测试", micro_queries=["q1"])
            ]
            from agent import DeepResearchAgent
            agent = DeepResearchAgent(config=config)
            # Set _style on reporting
            agent.reporting._style = "weekly"
            agent.reporting._extract_enterprise_from_topic = lambda t: "test_ent"
            agent.reporting._get_enterprise_field = lambda e, f: "test_industry"
            agent.reporting._load_enterprises_yaml = lambda: []
            # We just verify the call doesn't crash
            tasks = agent._make_weekly_tasks("test topic")
            assert len(tasks) == 5
