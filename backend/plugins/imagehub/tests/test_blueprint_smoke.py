class TestImageHubBlueprintRegistered:
    def test_ui_unauthenticated_redirects(self, client):
        """The blueprint is mounted and its auth guard works."""
        assert client.get("/imagehub/ui").status_code == 302
