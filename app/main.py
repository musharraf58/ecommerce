from fastapi import FastAPI
from app.routers import auth,products, cart,orders, payments
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="E-commerce API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(cart.router)
app.include_router(products.category_router)
app.include_router(orders.router)
app.include_router(payments.router)

@app.get("/health")
def health_check():
    return {"status": "healthy"}