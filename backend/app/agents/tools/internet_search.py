from enum import Enum
from typing import List, Dict, Optional
from pydantic import BaseModel, Field, root_validator
from app.agents.tools.agent_tool import AgentTool
from app.repositories.models.custom_bot import BotModel
from app.routes.schemas.conversation import type_model_name
import wikipediaapi
import requests
from duckduckgo_search import DDGS

# Search engine options
class SearchEngine(str, Enum):
    DUCKDUCKGO = "duckduckgo"
    WIKIPEDIA = "wikipedia"
    SEARX = "searx"
    QWANT = "qwant"

# Country codes
class CountryCode(str, Enum):
    TAIWAN = "tw-zh"
    JAPAN = "jp-jp"
    KOREA = "kr-kr"
    CHINA = "cn-zh"
    FRANCE = "fr-fr"
    GERMANY = "de-de"
    SPAIN = "es-es"
    ITALY = "it-it"
    USA = "us-en"

class InternetSearchInput(BaseModel):
    query: str = Field(description="The query to search for on the internet.")
    country: str = Field(
        description="The country code you wish for search. Must be one of: "
                   "tw-zh (Taiwan), jp-jp (Japan), kr-kr (Korea), cn-zh (China), "
                   "fr-fr (France), de-de (Germany), es-es (Spain), it-it (Italy), "
                   "us-en (United States)"
    )
    time_limit: str = Field(
        description="The time limit for the search. Options are 'd' (day), 'w' (week), 'm' (month), 'y' (year)."
    )
    engine: SearchEngine = Field(
        default=SearchEngine.DUCKDUCKGO,
        description="The search engine to use"
    )

    @root_validator(pre=True)
    def validate_country(cls, values):
        country = values.get("country")
        valid_countries = [code.value for code in CountryCode]
        if country not in valid_countries:
            raise ValueError(
                "Country must be one of: "
                "tw-zh (Taiwan), jp-jp (Japan), kr-kr (Korea), cn-zh (China), "
                "fr-fr (France), de-de (Germany), es-es (Spain), it-it (Italy), "
                "us-en (United States)"
            )
        return values

class SearchEngineImplementation:
    @staticmethod
    def duckduckgo_search(query: str, country: str, time_limit: str) -> List[Dict]:
        try:
            with DDGS() as ddgs:
                return [
                    {
                        "content": result["body"],
                        "source_name": result["title"],
                        "source_link": result["href"],
                    }
                    for result in ddgs.text(
                        keywords=query,
                        region=country,
                        safesearch="moderate",
                        timelimit=time_limit,
                        max_results=20,
                        backend="api",
                    )
                ]
        except Exception as e:
            print(f"DuckDuckGo search error: {str(e)}")
            return []

    @staticmethod
    def wikipedia_search(query: str, language: str = "en") -> List[Dict]:
        try:
            wiki = wikipediaapi.Wikipedia(language)
            page = wiki.page(query)
            
            if page.exists():
                return [{
                    "content": page.summary,
                    "source_name": page.title,
                    "source_link": page.fullurl
                }]
            return []
        except Exception as e:
            print(f"Wikipedia search error: {str(e)}")
            return []

    @staticmethod
    def searx_search(query: str, instance_url: str = "https://searx.be") -> List[Dict]:
        try:
            response = requests.get(
                f"{instance_url}/search",
                params={"q": query, "format": "json"},
                timeout=10
            )
            results = response.json()
            
            return [{
                "content": result.get("content", ""),
                "source_name": result.get("title", ""),
                "source_link": result.get("url", "")
            } for result in results.get("results", [])]
        except Exception as e:
            print(f"Searx search error: {str(e)}")
            return []

    @staticmethod
    def qwant_search(query: str) -> List[Dict]:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            response = requests.get(
                "https://api.qwant.com/v3/search/web",
                headers=headers,
                params={"q": query, "locale": "en_US", "count": 10},
                timeout=10
            )
            results = response.json()
            
            return [{
                "content": item.get("description", ""),
                "source_name": item.get("title", ""),
                "source_link": item.get("url", "")
            } for item in results.get("data", {}).get("result", {}).get("items", [])]
        except Exception as e:
            print(f"Qwant search error: {str(e)}")
            return []

def internet_search(
    tool_input: InternetSearchInput,
    bot: Optional[BotModel] = None,
    model: Optional[type_model_name] = None
) -> List[Dict]:
    query = tool_input.query
    country = tool_input.country
    time_limit = tool_input.time_limit
    engine = tool_input.engine

    # Define search engine implementation mapping
    search_implementations = {
        SearchEngine.DUCKDUCKGO: lambda: SearchEngineImplementation.duckduckgo_search(
            query, country, time_limit
        ),
        SearchEngine.WIKIPEDIA: lambda: SearchEngineImplementation.wikipedia_search(
            query, country.split("-")[1]
        ),
        SearchEngine.SEARX: lambda: SearchEngineImplementation.searx_search(query),
        SearchEngine.QWANT: lambda: SearchEngineImplementation.qwant_search(query),
    }

    # Try using the selected search engine
    try:
        results = search_implementations[engine]()
        if results:
            return results
    except Exception as e:
        print(f"Error with {engine}: {str(e)}")

    # If primary search engine fails, try other engines as backup
    for backup_engine, search_func in search_implementations.items():
        if backup_engine != engine:
            try:
                results = search_func()
                if results:
                    return results
            except Exception as e:
                print(f"Backup search error with {backup_engine}: {str(e)}")
                continue

    return []  # Return empty list if all searches fail

# Register tool
internet_search_tool = AgentTool(
    name="internet_search",
    description="Search the internet for information using multiple search engines.",
    args_schema=InternetSearchInput,
    function=internet_search,
)