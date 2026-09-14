from fastapi import FastAPI
from app.routers import auth,products, cart

app = FastAPI(title="E-commerce API")

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(cart.router)
app.include_router(products.category_router)

@app.get("/health")
def health_check():
    return {"status": "healthy"}