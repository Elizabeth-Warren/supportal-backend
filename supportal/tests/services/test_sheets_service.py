import unittest

from supportal.services.google_sheets_service import GoogleSheetsClient


@unittest.mock.patch("supportal.services.google_sheets_service.Credentials")
@unittest.mock.patch("supportal.services.google_sheets_service.pygsheets.client.Client")
def test_get_values_from_sheet(*args, **kwargs):
    client = GoogleSheetsClient("{}")
    mock_client = client.client
    spreadsheet_mock = unittest.mock.MagicMock()
    worksheet_mock = unittest.mock.MagicMock()

    mock_client.open_by_url.return_value = spreadsheet_mock
    spreadsheet_mock.worksheet_by_title.return_value = worksheet_mock
    worksheet_mock.get_all_records.return_value = [
        {"column1": "val", "column2": "val2"},
        {"column1": ""},
    ]
    results = client.get_values_from_sheet("fake", "tab", ["column1"])

    assert len(results) == 2
    for resp in results:
        assert "column1" in resp
        assert "column2" not in resp

    mock_client.open_by_url.assert_called_with("fake")
    spreadsheet_mock.worksheet_by_title.assert_called_with("tab")
    worksheet_mock.get_all_records.assert_called_with()
