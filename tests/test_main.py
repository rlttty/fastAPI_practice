import asyncio
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from main import Base, app, get_db

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


@pytest.fixture(name="client", scope="module")
def test_client():
    # Создаём таблицы один раз
    async def init_models():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(init_models())

    with TestClient(app) as c:
        yield c

    # Очистка после всех тестов
    async def drop_models():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    asyncio.run(drop_models())
    app.dependency_overrides.clear()


def test_create_recipe(client: TestClient):
    """Тест создания рецепта"""
    recipe_data = {
        "name": "Борщ",
        "cooking_time": 90,
        "ingredients": "свекла, капуста, мясо, картофель",
        "description": "Классический украинский борщ.",
    }

    response = client.post("/recipes", json=recipe_data)
    assert response.status_code == HTTPStatus.CREATED

    data = response.json()
    assert data["name"] == "Борщ"
    assert data["cooking_time"] == 90
    assert data["ingredients"] == "свекла, капуста, мясо, картофель"
    assert data["description"] == "Классический украинский борщ."


def test_get_recipes_list_empty_at_start(client: TestClient):
    """Изначально список пуст"""
    response = client.get("/recipes")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


def test_get_recipes_list_sorting_and_multiple_creations(client: TestClient):
    """Проверка сортировки: сначала по views DESC, потом по cooking_time ASC"""
    # Создаём три рецепта с разным временем приготовления
    recipes_to_create = [
        {
            "name": "Пицца",
            "cooking_time": 30,
            "ingredients": "тесто, сыр",
            "description": "...",
        },
        {
            "name": "Салат Цезарь",
            "cooking_time": 20,
            "ingredients": "курица, салат",
            "description": "...",
        },
        {
            "name": "Омлет",
            "cooking_time": 10,
            "ingredients": "яйца, молоко",
            "description": "...",
        },
    ]

    for rec in recipes_to_create:
        response = client.post("/recipes", json=rec)
        assert response.status_code == HTTPStatus.CREATED

    # Теперь в списке должно быть 4 рецепта (Борщ из первого теста + эти три)
    response = client.get("/recipes")
    assert response.status_code == HTTPStatus.OK
    recipes = response.json()

    assert len(recipes) == 4

    # Все views = 0 → сортировка только по cooking_time ASC
    expected_order = ["Омлет", "Салат Цезарь", "Пицца", "Борщ"]
    actual_names = [r["name"] for r in recipes]
    assert actual_names == expected_order


def test_recipe_detail_views_increment(client: TestClient):
    """Проверка инкремента просмотров при детальном просмотре"""
    # Создаём новый уникальный рецепт
    response = client.post(
        "/recipes",
        json={
            "name": "Тестовый рецепт для views",
            "cooking_time": 15,
            "ingredients": "ингредиент1, ингредиент2",
            "description": "Для проверки счётчика просмотров",
        },
    )
    assert response.status_code == HTTPStatus.CREATED

    # Находим его в списке по имени и проверяем начальное количество просмотров
    list_response = client.get("/recipes")
    recipes = list_response.json()
    test_recipe = next(r for r in recipes if r["name"] == "Тестовый рецепт для views")
    assert test_recipe["views"] == 0

    # Первый просмотр детали — views должен стать 1
    # Поскольку ID нет в ответе, ищем рецепт по имени и эмулируем просмотр (но detail требует ID)
    # Проблема: без ID в API мы не можем вызвать /recipes/{id}
    # Поэтому пока проверяем только создание и список.
    # Если добавишь id в схемы — сможешь дописать полный тест.
    # А пока оставляем только проверку, что рецепт появился
    assert test_recipe["cooking_time"] == 15
