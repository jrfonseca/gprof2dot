import pytest


def pytest_addoption(parser):
    parser.addoption(
        '--force-refs',
        action='store_true',
        default=False,
        help='(re)generate the reference outputs instead of checking against them')


@pytest.fixture
def force_refs(request):
    return request.config.getoption('--force-refs')
