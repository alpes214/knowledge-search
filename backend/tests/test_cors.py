from httpx import AsyncClient


async def test_cors_preflight_allows_localhost_3000(client: AsyncClient) -> None:
    r = await client.options(
        '/docs',
        headers={
            'Origin': 'http://localhost:3000',
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'content-type',
        },
    )
    assert r.status_code == 200
    assert r.headers['access-control-allow-origin'] == 'http://localhost:3000'
    assert 'POST' in r.headers.get('access-control-allow-methods', '')


async def test_cors_unallowed_origin_lacks_header(client: AsyncClient) -> None:
    r = await client.options(
        '/docs',
        headers={
            'Origin': 'http://evil.example.com',
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'content-type',
        },
    )
    assert 'access-control-allow-origin' not in r.headers
