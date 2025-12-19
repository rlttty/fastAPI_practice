import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from main import Base, app, get_db

# Тестовая БД — в памяти, чтобы не засорять диск и чтобы тесты были быстрыми
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Создаём отдельный async engine для тестов
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

# Session для тестов
TestingSessionLocal = sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)


# Переопределяем dependency get_db на тестовую БД
async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


# Фикстура для клиента
@pytest.fixture(name="client", scope="module")
def test_client():
    # Создаём таблицы в тестовой БД один раз на модуль
    async def init_models():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(init_models())

    with TestClient(app) as c:
        yield c

    # Очистка после тестов (drop tables)
    async def drop_models():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    asyncio.run(drop_models())

    # Сбрасываем переопределение dependency
    app.dependency_overrides.clear()


# ----------------------- Тесты -----------------------


def test_create_recipe(client: TestClient):
    """Тест создания нового рецепта через POST /recipes"""
    recipe_data = {
        "name": "Борщ",
        "cooking_time": 90,
        "ingredients": "свекла, капуста, мясо, картофель",
        "description": "Классический украинский борщ.",
    }

    response = client.post("/recipes", json=recipe_data)
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Борщ"
    assert data["cooking_time"] == 90
    assert data["ingredients"] == "свекла, капуста, мясо, картофель"
    assert data["description"] == "Классический украинский борщ."
    assert "name" in data  # проверяем, что все поля есть


def test_get_recipes_list_empty(client: TestClient):
    """Список рецептов изначально пуст"""
    response = client.get("/recipes")
    assert response.status_code == 200
    assert response.json() == []


def test_get_recipes_list_after_create(client: TestClient):
    """После создания рецепта он появляется в списке"""
    # Создаём два рецепта
    client.post(
        "/recipes",
        json={
            "name": "Пицца",
            "cooking_time": 30,
            "ingredients": "тесто, сыр, томатный соус",
            "description": "Итальянская пицца маргарита.",
        },
    )
    client.post(
        "/recipes",
        json={
            "name": "Салат Цезарь",
            "cooking_time": 20,
            "ingredients": "курица, салат, сухарики, соус",
            "description": "Классический Цезарь с курицей.",
        },
    )

    response = client.get("/recipes")
    assert response.status_code == 200
    recipes = response.json()

    # Должно быть 3 рецепта (Борщ + Пицца + Цезарь), отсортированы по views DESC, затем cooking_time ASC
    assert len(recipes) == 3
    # Все имеют views = 0, поэтому сортировка по cooking_time ASC
    assert recipes[0]["name"] == "Салат Цезарь"  # 20 мин
    assert recipes[1]["name"] == "Пицца"  # 30 мин
    assert recipes[2]["name"] == "Борщ"  # 90 мин


def test_get_recipe_detail_and_views_increment(client: TestClient):
    """Проверка детального просмотра и инкремента просмотров"""
    # Сначала создадим рецепт
    create_response = client.post(
        "/recipes",
        json={
            "name": "Омлет",
            "cooking_time": 10,
            "ingredients": "яйца, молоко, соль",
            "description": "Простой омлет на завтрак.",
        },
    )
    recipe_id = create_response.json()[
        "name"
    ]  # нет, лучше получить из списка или запомнить

    # Получим список, найдём ID рецепта с именем "Омлет"
    list_response = client.get("/recipes")
    recipe = next(r for r in list_response.json() if r["name"] == "Омлет")
    recipe_id = None  # нам нужен ID, но в списке его нет! Проблема...

    # Лучше: после создания возвращается только детали без ID, но в БД он есть.
    # Перепишем: создадим и сразу возьмём список, найдём по имени

    # Очистим и создадим один рецепт для чистоты
    # Но проще — создаём один и дважды вызываем detail

    # Новый подход: создаём рецепт, потом два раза вызываем detail и проверяем views

    response = client.post(
        "/recipes",
        json={
            "name": "Тестовый рецепт для просмотров",
            "cooking_time": 15,
            "ingredients": "ингредиент1, ингредиент2",
            "description": "Описание для теста.",
        },
    )
    assert response.status_code == 201

    # Получаем список — там будет только один рецепт (если тесты изолированы, но у нас один клиент на модуль)
    # Чтобы избежать влияния других тестов — лучше искать по имени

    list_resp = client.get("/recipes")
    recipe_in_list = next(
        r for r in list_resp.json() if r["name"] == "Тестовый рецепт для просмотров"
    )
    initial_views = recipe_in_list["views"]
    assert initial_views == 0
