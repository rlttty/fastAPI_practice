from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite+aiosqlite:///./culinary_book.db"
engine = create_async_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


# Модель SQLAlchemy для рецепта
class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)  # Название рецепта
    views = Column(
        Integer, default=0
    )  # Количество просмотров (сколько раз открыли детальный рецепт)
    cooking_time = Column(Integer)  # Время приготовления в минутах
    ingredients = Column(
        Text
    )  # Список ингредиентов, хранится как строка с разделителями запятыми для простоты
    description = Column(Text)  # Текстовое описание рецепта


# Модели Pydantic для схем API


class RecipeCreate(BaseModel):
    """
    Схема для создания нового рецепта через POST-запрос.
    """

    name: str = Field(
        ..., min_length=1, max_length=255, description="Название рецепта."
    )
    cooking_time: int = Field(..., gt=0, description="Время приготовления в минутах.")
    ingredients: str = Field(
        ..., description="Список ингредиентов, разделенных запятыми."
    )
    description: str = Field(..., description="Подробное текстовое описание рецепта.")


class RecipeListItem(BaseModel):
    """
    Схема для элементов списка рецептов в эндпоинте списка.
    Включает поля, видимые в таблице списка рецептов.
    """

    name: str = Field(..., description="Название рецепта.")
    views: int = Field(..., description="Количество просмотров (популярность).")
    cooking_time: int = Field(..., description="Время приготовления в минутах.")


class RecipeDetail(BaseModel):
    """
    Схема для детальной информации о рецепте.
    Включает все поля для экрана детального просмотра рецепта.
    """

    name: str = Field(..., description="Название рецепта.")
    cooking_time: int = Field(..., description="Время приготовления в минутах.")
    ingredients: str = Field(
        ..., description="Список ингредиентов, разделенных запятыми."
    )
    description: str = Field(..., description="Подробное текстовое описание рецепта.")


app = FastAPI(
    title="API Кулинарной Книги",
    description="API для управления кулинарной книгой с рецептами. Поддерживает список рецептов, отсортированный по популярности, просмотр деталей (с инкрементом просмотров) и создание новых рецептов.",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI для документации
    redoc_url="/redoc",  # ReDoc для альтернативной документации
)


async def get_db():
    async with SessionLocal() as session:
        yield session


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# Эндпоинты


@app.get(
    "/recipes",
    response_model=list[RecipeListItem],
    summary="Получить список всех рецептов",
    description="Возвращает список всех рецептов, отсортированный по популярности (просмотры по убыванию), затем по времени приготовления по возрастанию в случае равенства. Этот эндпоинт питает основной экран с таблицей рецептов.",
)
async def get_recipes(db: AsyncSession = Depends(get_db)):
    # Запрос рецептов, отсортированных по views DESC, затем cooking_time ASC
    stmt = select(Recipe).order_by(Recipe.views.desc(), Recipe.cooking_time.asc())
    result = await db.execute(stmt)
    recipes = result.scalars().all()
    return [
        RecipeListItem(name=r.name, views=r.views, cooking_time=r.cooking_time)
        for r in recipes
    ]


@app.get(
    "/recipes/{recipe_id}",
    response_model=RecipeDetail,
    summary="Получить детальную информацию о конкретном рецепте",
    description="Возвращает детальную информацию о рецепте по ID. Инкрементирует счетчик просмотров каждый раз при вызове этого эндпоинта. Это питает экран детального просмотра рецепта.",
)
async def get_recipe_detail(recipe_id: int, db: AsyncSession = Depends(get_db)):
    # Получение рецепта
    stmt = select(Recipe).where(Recipe.id == recipe_id)
    result = await db.execute(stmt)
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Рецепт не найден"
        )

    # Инкремент просмотров
    recipe.views += 1
    await db.commit()

    # Возврат схемы деталей
    return RecipeDetail(
        name=recipe.name,
        cooking_time=recipe.cooking_time,
        ingredients=recipe.ingredients,
        description=recipe.description,
    )


@app.post(
    "/recipes",
    response_model=RecipeDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Создать новый рецепт",
    description="Создает новый рецепт с предоставленными данными. Возвращает детали созданного рецепта.",
)
async def create_recipe(recipe: RecipeCreate, db: AsyncSession = Depends(get_db)):
    # Создание новой инстанции рецепта
    new_recipe = Recipe(
        name=recipe.name,
        cooking_time=recipe.cooking_time,
        ingredients=recipe.ingredients,
        description=recipe.description,
        views=0,  # Начинает с 0 просмотров
    )
    db.add(new_recipe)
    await db.commit()
    await db.refresh(new_recipe)

    # Возврат созданного рецепта
    return RecipeDetail(
        name=new_recipe.name,
        cooking_time=new_recipe.cooking_time,
        ingredients=new_recipe.ingredients,
        description=new_recipe.description,
    )
