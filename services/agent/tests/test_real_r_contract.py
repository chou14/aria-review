import httpx
import pytest
import pytest_asyncio

from app.r_client import RClient


pytestmark = pytest.mark.real_r


@pytest_asyncio.fixture
async def real_r_client(real_r_base_url):
    """用真实 plumber base_url 构造 agent RClient。"""
    async with httpx.AsyncClient(base_url=real_r_base_url, timeout=90) as client:
        yield RClient(client)


def _sample_records() -> list[dict]:
    """小而完整的结构化题录，与 get_corpus_records 真实形状对齐（引用在 csl_json.references，字符串数组）。"""
    return [
        {
            "title": "Bibliometric study of science mapping",
            "creators": [
                {"family": "Aria", "given": "Massimo"},
                {"family": "Cuccurullo", "given": "Corrado"},
            ],
            "year": 2017,
            "doi": "10.1016/j.joi.2017.08.007",
            "abstract": "A compact bibliometric study used for contract testing.",
            "keywords": ["bibliometrics", "science mapping"],
            "container_title": "Journal of Informetrics",
            "csl_json": {"references": [
                "SMALL H, 1973, J AM SOC INF SCI",
                "GARFIELD E, 1955, SCIENCE",
            ]},
        },
        {
            "title": "Mapping research fronts with bibliometric methods",
            "creators": [
                {"family": "Smith", "given": "Jane"},
                {"family": "Aria", "given": "Massimo"},
            ],
            "year": 2020,
            "doi": "10.1234/bibliocn.2020.001",
            "abstract": "Research fronts can be explored with co-word analysis.",
            "keywords": ["bibliometrics", "co-word analysis"],
            "container_title": "Scientometrics",
            "csl_json": {"references": [
                "SMALL H, 1973, J AM SOC INF SCI",
                "VAN ECK NJ, 2010, SCIENTOMETRICS",
            ]},
        },
        {
            "title": "Author keyword evolution in digital libraries",
            "creators": [
                {"family": "Lee", "given": "Kai"},
            ],
            "year": 2022,
            "doi": "10.1234/bibliocn.2022.002",
            "abstract": "Keyword evolution describes changes in a research field.",
            "keywords": ["digital libraries", "science mapping"],
            "container_title": "Information Processing and Management",
            "csl_json": {"references": [
                "GARFIELD E, 1955, SCIENCE",
            ]},
        },
    ]


async def _create_real_corpus(real_r_client: RClient) -> tuple[str, dict]:
    status, body = await real_r_client.parse_from_records(_sample_records())
    assert status == 200, body
    assert isinstance(body, dict)
    corpus_id = body.get("corpusId")
    assert isinstance(corpus_id, str) and corpus_id
    return corpus_id, body


@pytest.mark.asyncio
async def test_real_r_parse_from_records_contract(real_r_client):
    status, body = await real_r_client.parse_from_records(_sample_records())

    assert status == 200, body
    assert isinstance(body, dict)
    assert isinstance(body.get("corpusId"), str)
    assert body["status"] == "ready"
    assert body["documentCount"] == len(_sample_records())
    assert body["dbsource"] == "bibliocn"
    assert isinstance(body["schemaVersion"], int)
    assert isinstance(body["createdAt"], str)


@pytest.mark.asyncio
async def test_real_r_records_contract(real_r_client):
    corpus_id, _ = await _create_real_corpus(real_r_client)

    status, body = await real_r_client.get_records(corpus_id, limit=2)

    assert status == 200, body
    assert isinstance(body, dict)
    assert body["corpusId"] == corpus_id
    assert isinstance(body["records"], list)
    assert 1 <= len(body["records"]) <= 2

    record = body["records"][0]
    assert isinstance(record["idx"], int)
    assert isinstance(record["title"], str)
    assert isinstance(record["authors"], str)
    assert isinstance(record["year"], int)
    assert isinstance(record.get("doi"), str)


@pytest.mark.asyncio
async def test_real_r_search_openalex_limit_validation_contract(real_r_client):
    status, body = await real_r_client.search_openalex(
        query="bibliometrics",
        n=501,
        since="2020",
    )

    assert status == 400, body
    assert isinstance(body, dict)
    assert body["error"] == "VALIDATION_ERROR"
    assert isinstance(body["detail"], str)
    assert "<= 500" in body["detail"]


@pytest.mark.asyncio
async def test_real_r_keyword_trend_envelope_contract(real_r_client):
    corpus_id, _ = await _create_real_corpus(real_r_client)

    status, body = await real_r_client.get_keyword_trend(corpus_id)

    assert status == 200, body
    assert isinstance(body, dict)
    assert body["corpusId"] == corpus_id
    assert isinstance(body["schemaVersion"], int)
    assert isinstance(body["available"], bool)
    if body["available"]:
        assert isinstance(body["data"], dict)
    else:
        assert isinstance(body["reason"], str)
        assert isinstance(body["message"], str)
