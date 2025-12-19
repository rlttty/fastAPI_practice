from typing import Annotated

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


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    views = Column(Integer, default=0)
    cooking_time = Column(Integer)
    ingredients = Column(Text)
    description = Column(Text)


class RecipeCreate(BaseModel):
    name: str = Field(
        ..., min_length=1, max_length=255, description="Название рецепта."
    )
    cooking_time: int = Field(..., gt=0, description="Время приготовления в минутах.")
    ingredients: str = Field(
        ..., description="Список ингредиентов, разделенных запятыми."
    )
    description: str = Field(..., description="Подробное текстовое описание рецепта.")


class RecipeListItem(BaseModel):
    name: str = Field(..., description="Название рецепта.")
    views: int = Field(..., description="Количество просмотров (популярность).")
    cooking_time: int = Field(..., description="Время приготовления в минутах.")


class RecipeDetail(BaseModel):
    name: str = Field(..., description="Название рецепта.")
    cooking_time: int = Field(..., description="Время приготовления в минутах.")
    ingredients: str = Field(
        ..., description="Список ингредиентов, разделенных запятыми."
    )
    description: str = Field(..., description="Подробное текстовое описание рецепта.")


app = FastAPI(
    title="API Кулинарной Книги",
    description="API для управления кулинарной книгой с рецептами.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


async def get_db():
    async with SessionLocal() as session:
        yield session


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# Ключевой фикс: используем Annotated + Depends
DbSession = Annotated[AsyncSession, Depends(get_db)]


@app.get("/recipes", response_model=list[RecipeListItem])
async def get_recipes(db: DbSession):
    stmt = select(Recipe).order_by(Recipe.views.desc(), Recipe.cooking_time.asc())
    result = await db.execute(stmt)
    recipes = result.scalars().all()
    return [
        RecipeListItem(name=r.name, views=r.views, cooking_time=r.cooking_time)
        for r in recipes
    ]


@app.get("/recipes/{recipe_id}", response_model=RecipeDetail)
async def get_recipe_detail(recipe_id: int, db: DbSession):
    stmt = select(Recipe).where(Recipe.id == recipe_id)
    result = await db.execute(stmt)
    recipe = result.scalar_one_or_none()

    if not recipe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Рецепт не найден"
        )

    recipe.views += 1
    await db.commit()

    return RecipeDetail(
        name=recipe.name,
        cooking_time=recipe.cooking_time,
        ingredients=recipe.ingredients,
        description=recipe.description,
    )


@app.post("/recipes", response_model=RecipeDetail, status_code=status.HTTP_201_CREATED)
async def create_recipe(recipe: RecipeCreate, db: DbSession):
    new_recipe = Recipe(
        name=recipe.name,
        cooking_time=recipe.cooking_time,
        ingredients=recipe.ingredients,
        description=recipe.description,
        views=0,
    )
    db.add(new_recipe)
    await db.commit()
    await db.refresh(new_recipe)

    return RecipeDetail(
        name=new_recipe.name,
        cooking_time=new_recipe.cooking_time,
        ingredients=new_recipe.ingredients,
        description=new_recipe.description,
    )
