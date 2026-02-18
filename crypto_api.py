import aiohttp
import json
from datetime import datetime

class CryptoBotAPI:
    def __init__(self, token):
        self.token = token
        self.base_url = "https://pay.crypt.bot/api"
        self.headers = {
            "Crypto-Pay-API-Token": token,
            "Content-Type": "application/json"
        }
    
    async def create_check(self, amount, currency="USD", description=""):
        """Создание чека для оплаты"""
        url = f"{self.base_url}/createCheck"
        
        data = {
            "asset": currency,
            "amount": str(amount),
            "description": description,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get('result')
                else:
                    error = await response.text()
                    raise Exception(f"Ошибка API: {error}")
    
    async def get_check(self, check_id):
        """Получение информации о чеке"""
        url = f"{self.base_url}/getCheck"
        
        data = {
            "check_id": check_id
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get('result')
                return None
    
    async def check_payment_status(self, check_id):
        """Проверка статуса оплаты чека"""
        check = await self.get_check(check_id)
        if check:
            return {
                'status': check.get('status'),
                'paid_at': check.get('paid_at'),
                'paid_by': check.get('paid_by'),
                'amount': check.get('amount')
            }
        return None
