import asyncio
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from main import Base, app, get_db

# Константы для тестов
EXPECTED_RECIPES_IN_SORT_TEST = 3
INITIAL_VIEWS = 0
TEST_COOKING_TIME_FOR_VIEWS = 15
BORSHCH_COOKING_TIME = 90

# Тестовая БД в памяти
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)


async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(name="client", scope="function")
def test_client():
    async def init_models():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(init_models())

    with TestClient(app) as c:
        yield c

    async def drop_models():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    asyncio.run(drop_models())


def test_create_recipe(client: TestClient):
    """Тест создания одного рецепта"""
    recipe_data = {
        "name": "Борщ",
        "cooking_time": BORSHCH_COOKING_TIME,
        "ingredients": "свекла, капуста, мясо, картофель",
        "description": "Классический украинский борщ.",
    }

    response = client.post("/recipes", json=recipe_data)
    assert response.status_code == HTTPStatus.CREATED

    data = response.json()
    assert data["name"] == "Борщ"
    assert data["cooking_time"] == BORSHCH_COOKING_TIME
    assert data["ingredients"] == "свекла, капуста, мясо, картофель"
    assert data["description"] == "Классический украинский борщ."


def test_get_recipes_list_empty_at_start(client: TestClient):
    """Список рецептов изначально пуст"""
    response = client.get("/recipes")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


def test_get_recipes_list_sorting_and_multiple_creations(client: TestClient):
    """Проверка сортировки списка: views DESC → cooking_time ASC"""
    # Создаём три рецепта
    additional_recipes = [
        {
            "name": "Пицца",
            "cooking_time": 30,
            "ingredients": "тесто, сыр",
            "description": "Простая пицца.",
        },
        {
            "name": "Салат Цезарь",
            "cooking_time": 20,
            "ingredients": "курица, салат",
            "description": "Классический Цезарь.",
        },
        {
            "name": "Омлет",
            "cooking_time": 10,
            "ingredients": "яйца, молоко",
            "description": "Быстрый завтрак.",
        },
    ]

    for recipe in additional_recipes:
        response = client.post("/recipes", json=recipe)
        assert response.status_code == HTTPStatus.CREATED

    response = client.get("/recipes")
    assert response.status_code == HTTPStatus.OK
    recipes = response.json()

    assert len(recipes) == EXPECTED_RECIPES_IN_SORT_TEST

    # Сортировка по cooking_time ASC (все views = 0)
    expected_order = ["Омлет", "Салат Цезарь", "Пицца"]
    actual_names = [r["name"] for r in recipes]
    assert actual_names == expected_order


def test_recipe_appears_in_list_after_creation(client: TestClient):
    """Проверка, что новый рецепт появляется в списке и имеет views = 0"""
    response = client.post(
        "/recipes",
        json={
            "name": "Тестовый рецепт для views",
            "cooking_time": TEST_COOKING_TIME_FOR_VIEWS,
            "ingredients": "ингредиент1, ингредиент2",
            "description": "Для проверки появления в списке",
        },
    )
    assert response.status_code == HTTPStatus.CREATED

    list_response = client.get("/recipes")
    assert list_response.status_code == HTTPStatus.OK

    recipes = list_response.json()
    test_recipe = next(
        (r for r in recipes if r["name"] == "Тестовый рецепт для views"),
        None,
    )
    assert test_recipe is not None
    assert test_recipe["views"] == INITIAL_VIEWS
    assert test_recipe["cooking_time"] == TEST_COOKING_TIME_FOR_VIEWS
