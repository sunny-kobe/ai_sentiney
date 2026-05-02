"""Sentinel 自动研报模块"""

from src.report_gen.data_aggregator import DataAggregator
from src.report_gen.report_generator import ReportGenerator
from src.report_gen.runner import AutoReportRunner

__all__ = ["DataAggregator", "ReportGenerator", "AutoReportRunner"]
