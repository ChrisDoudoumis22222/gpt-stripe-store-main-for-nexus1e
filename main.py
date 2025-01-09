from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    servers=[
        {
            "url": "https://gpt-stripe-store-main-for-nexus1e-git-main-christoss-projects.vercel.app/",
            "description": "Production environment"
        }
    ]
)

# Serve static files
app.mount("/static", StaticFiles(directory="."), name="static")

# Define a dictionary to map moods to colors
mood_color_mapping = {
    "happy": "yellow",
    "sad": "blue",
    "angry": "red",
    "relaxed": "green",
    "excited": "orange",
    "bored": "gray"
}

@app.get("/getColorByMood")
async def get_color_by_mood(mood: str):
    mood = mood.lower()
    if mood in mood_color_mapping:
        return {"mood": mood, "color": mood_color_mapping[mood]}
    else:
        raise HTTPException(status_code=404, detail="Mood not found")

@app.get("/")
async def health_check():
    return {"message": "The getColorByMood API is live!"}
