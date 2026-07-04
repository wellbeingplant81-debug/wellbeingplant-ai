from google import genai

client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)

response = client.models.generate_images(
    model="imagen-4.0-generate-001",
    prompt="A realistic Korean doctor in a hospital, photorealistic",
)

print(response)
print(type(response))