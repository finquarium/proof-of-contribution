# finquarium_proof/models/insights.py
from datetime import datetime
from typing import List, Optional, Dict
from dataclasses import dataclass

@dataclass
class InsightsMetadata:
    """Metadata about the insights submission"""
    version: str
    timestamp: int
    basePoints: int
    predictionPoints: int

@dataclass
class MarketExperience:
    """User's experience in different markets"""
    marketExperience: Dict[str, str]
    background: str
    methodologies: List[str]

@dataclass
class Strategy:
    """User's trading strategy details"""
    riskManagement: str
    positionSizing: str
    technicalIndicators: List[str]
    entryExitStrategy: str

@dataclass
class Psychology:
    """User's trading psychology profile"""
    lossTolerance: int
    decisionProcess: str
    emotionalManagement: List[str]

@dataclass
class Contact:
    """User's contact preferences"""
    method: str
    value: str
    allowUpdates: bool

@dataclass
class MarketInsights:
    """Complete market insights submission"""
    metadata: InsightsMetadata
    expertise: MarketExperience
    strategy: Strategy
    psychology: Psychology
    contact: Optional[Contact] = None

# Database model
# finquarium_proof/models/db.py
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

