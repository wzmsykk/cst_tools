"""Shared metric vocabulary for GUI labels and CST VBA generation."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    query: str
    token: str
    label: str
    integration_line: bool = False


METRICS = {
    'Q_Factor': MetricDefinition('Q-Factor', 'Q_Factor', 'Q Factor'),
    'Q_Ext': MetricDefinition('Q_Ext', 'Q_Ext', 'External Q'),
    'Frequency': MetricDefinition('Frequency', 'Frequency', 'Frequency'),
    'Total_Loss': MetricDefinition('Total Loss', 'Total_Loss', 'Total Loss'),
    'Loss_Enclosure': MetricDefinition('Loss_Enclosure', 'Loss_Enclosure', 'Enclosure Loss'),
    'Loss_Volume': MetricDefinition('Loss_Volume', 'Loss_Volume', 'Volume Loss'),
    'Loss_Surface': MetricDefinition('Loss_Surface', 'Loss_Surface', 'Surface Loss'),
    'Q_Enclosure': MetricDefinition('Q_Enclosure', 'Q_Enclosure', 'Enclosure Q'),
    'Q_Volume': MetricDefinition('Q_Volume', 'Q_Volume', 'Volume Q'),
    'Q_Surface': MetricDefinition('Q_Surface', 'Q_Surface', 'Surface Q'),
    'Total_Energy': MetricDefinition('Total Energy', 'Total_Energy', 'Total Energy'),
    'R_over_Q': MetricDefinition('R over Q', 'ROQ', 'R/Q', True),
    # Keep the vendor query spelling; it is not a user-facing label.
    'Shunt_Impedance': MetricDefinition('Shunt Inpedence', 'SI', 'Shunt Impedance', True),
}


def uses_integration_line(method: str) -> bool:
    base = method[:-4] if method.endswith('_All') else method
    metric = METRICS.get(base)
    return metric is not None and metric.integration_line
