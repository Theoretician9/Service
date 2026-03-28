from app.miniservices.engine import load_manifest, get_next_question, all_required_collected


class TestManifestLoading:
    def test_load_goal_setting_manifest(self):
        manifest = load_manifest("goal_setting")
        assert manifest["id"] == "goal_setting"
        assert manifest["credit_cost"] == 1

    def test_load_all_manifests(self):
        from app.miniservices.engine import get_all_manifests
        manifests = get_all_manifests()
        assert len(manifests) == 6

    def test_manifest_has_required_fields(self):
        manifest = load_manifest("supplier_search")
        assert "input_schema" in manifest
        assert "question_plan" in manifest
        assert "llm_config" in manifest


class TestQuestionPlan:
    def test_first_question_returned(self):
        question = get_next_question("goal_setting", {})
        assert question is not None
        assert question["id"] == "user_role"

    def test_no_question_when_all_collected(self):
        fields = {
            "user_role": "Предприниматель",
            "experience_context": "5 лет в IT",
            "desired_result": "Увеличить доход",
            "timeline": "3 месяца",
        }
        assert all_required_collected("goal_setting", fields)

    def test_conditional_field_skipped(self):
        question = get_next_question(
            "lead_search",
            {"product_offer": "test", "lead_source": "Искать в публичных источниках"},
        )
        assert question is not None
        assert question["id"] != "source_content"
