import os
from src.providers.voice_provider import VoiceProvider
from src.config import settings

def test():
    print(f"settings.twilio_phone_number: {settings.twilio_phone_number}")
    provider = VoiceProvider({})
    print(f"provider.from_number: {provider.from_number}")

if __name__ == "__main__":
    test()
