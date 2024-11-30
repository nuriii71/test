from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, timezone
import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
INCOME_URL = "https://kageherostudio.com/event/?event=daily"
XSS_LOGIN = "https://kageherostudio.com/payment/server_.php?fbid={}&selserver=1"
CLAIM_REWARD_URL = "https://kageherostudio.com/event/index_.php?act=daily"  # URL for claiming rewards
TIMEOUT = httpx.Timeout(60 * 5)

# Use timezone-aware datetime
DATE = datetime.now(timezone.utc) + timedelta(hours=7)  # GMT + 7 datetime

app = FastAPI()

class NhIncome:
    def __init__(self, email: str, server: int) -> None:
        self.email = email
        self.server = server
        self.cookies = None
        self.account_info = ""

    async def reserve_cookie(self, client: httpx.AsyncClient):
        await client.get(INCOME_URL)
        await client.get(XSS_LOGIN.format(self.email))
        self.cookies = client.cookies
        logger.info(f"Cookies reserved for {self.email}")

    async def check_daily(self, item_id: str):
        async with httpx.AsyncClient(timeout=TIMEOUT, cookies=self.cookies) as client:
            if not self.cookies:
                await self.reserve_cookie(client)

            resp = await client.get(INCOME_URL)
            html_content = await resp.aread()
            soup = BeautifulSoup(html_content, 'html.parser')

            # Get account info from the dropdown
            self.extract_account_info(soup)

            rewards = soup.find_all('div', class_='reward-content dailyClaim reward-star')

            if not rewards:
                logger.info("All rewards have already been claimed.")
                return {"message": "All rewards have already been claimed."}

            claimed_rewards = []
            for reward in rewards:
                reward_id = reward['data-id']  # Get the reward ID
                period_id = reward['data-period']  # Get the period ID
                reward_name = reward['data-name']  # Get the reward name
                reward_point_text = reward.find('div', class_='reward-point').text  # Get the reward point text
                day_number = int(reward_point_text.split('-')[1])

                # Check if the current reward matches the item_id
                if reward_id == item_id:
                    logger.info(f"Claiming reward: {reward_name}")
                    claim_result = await self.claim_reward(client, reward_id, period_id, reward_name, day_number)
                    if claim_result:
                        claimed_rewards.append(claim_result)  # Append the claim result
                    break  # Exit loop after claiming the specific item

            return {"email": self.email, "account_info": self.account_info, "server": self.server, "claimed_rewards": claimed_rewards}

    def extract_account_info(self, soup: BeautifulSoup):
        server_options = soup.find('select', {'name': 'selserver'}).find_all('option')
        for option in server_options:
            if option['value'] == str(self.server):
                self.account_info = option['data-server']
                break

    async def claim_reward(self, client: httpx.AsyncClient, item_id: str, period_id: str, reward_name: str, day_number: int):
        data = {
            'itemId': item_id,
            'periodId': period_id,
            'selserver': self.server
        }

        response = await client.post(CLAIM_REWARD_URL, data=data)

        if response.status_code == 200:
            logger.info(f"Successfully claimed reward for {self.email}: {reward_name}")
            return {
                "day": day_number,
                "item_name": reward_name,
                "total_claimed": day_number
            }
        else:
            logger.error(f"Failed to claim reward ID: {item_id}, Status Code: {response.status_code}, Response: {response.text}")
            raise HTTPException(status_code=response.status_code, detail=f"Failed to claim reward ID: {item_id}, Status Code: {response.status_code}")

@app.get("/claim_rewards")
async def claim_rewards(email: str, server: int, itemid: str):
    nh_income = NhIncome(email, server)
    result = await nh_income.check_daily(item_id=itemid)  # Pass item_id to the check_daily method
    return result  # Return the entire result including claimed rewards

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
