import pytest

from app.business import ItemCreate, ItemUpdate
from app.services import ServiceError, create_item, list_items, update_item


def test_item_services_scope_reads_and_writes_to_the_owner(test_context) -> None:
    """Ensure item services enforce ownership for reads and writes."""
    with test_context.session_factory() as session:
        item = create_item(
            test_context.user_ids["alice"],
            ItemCreate(title="  Service isolé  "),
            session,
        )
        session.commit()

        assert item["title"] == "Service isolé"
        assert [row["id"] for row in list_items(test_context.user_ids["alice"], session)] == [item["id"]]
        assert list_items(test_context.user_ids["bob"], session) == []

        with pytest.raises(ServiceError) as error:
            update_item(test_context.user_ids["bob"], item["id"], ItemUpdate(title="Intrusion"), session)
        assert error.value.status_code == 404
        assert error.value.detail == "Item not found."
