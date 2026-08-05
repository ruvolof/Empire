from empire.server.api.v2.shared_dependencies import paginate


class TestPaginate:
    def test_returns_page_and_total_pages_for_normal_limit(self):
        assert paginate(total=100, page=1, limit=10) == (1, 10)

    def test_rounds_up_partial_final_page(self):
        assert paginate(total=95, page=1, limit=10) == (1, 10)

    def test_zero_total_yields_zero_pages(self):
        assert paginate(total=0, page=1, limit=10) == (1, 0)

    def test_negative_limit_collapses_to_single_page(self):
        # -1 is the project's "unbounded" sentinel.
        assert paginate(total=500, page=1, limit=-1) == (1, 1)

    def test_zero_limit_collapses_to_single_page(self):
        assert paginate(total=10, page=1, limit=0) == (1, 1)

    def test_unbounded_with_empty_result_reports_zero_pages(self):
        assert paginate(total=0, page=1, limit=-1) == (1, 0)

    def test_unbounded_normalizes_requested_page_to_one(self):
        # A non-positive limit returns the whole dataset on a single page,
        # so a `?page=3` request is normalized rather than echoed back.
        assert paginate(total=500, page=3, limit=-1) == (1, 1)

    def test_echoes_requested_page_for_positive_limit(self):
        # With a bounded limit, the caller's page is passed through unchanged.
        assert paginate(total=100, page=3, limit=10) == (3, 10)
