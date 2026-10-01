from sqlalchemy import text


async def test_postgresql_extension_json_and_uuid(db_session):
    assert (await db_session.execute(text("SELECT '[1,2]'::vector <=> '[1,2]'::vector"))).scalar_one() == 0
    assert (await db_session.execute(
        text("SELECT CAST(:value AS jsonb) ->> 'key'"), {"value": '{"key":1}'}
    )).scalar_one() == "1"
