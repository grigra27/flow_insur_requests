#!/bin/bash
"""
Setup script for domain monitoring on Timeweb deployment
"""

set -e

echo "Setting up domain monitoring for insflow.tw1.su..."

# Create logs directory if it doesn't exist
mkdir -p /app/logs

# Set proper permissions for log files
touch /app/logs/domain_monitoring.log
touch /app/logs/domain_monitoring_results.json
touch /app/logs/landing.log
touch /app/logs/domain_routing.log
touch /app/logs/security.log

# Make monitoring script executable
chmod +x /app/monitor_domains.py

# Copy systemd service file (if running with systemd)
if command -v systemctl &> /dev/null; then
    echo "Setting up systemd service..."
    cp /app/scripts/domain-monitor.service /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable domain-monitor.service
    echo "Domain monitoring service installed. Start with: systemctl start domain-monitor"
else
    echo "Systemd not available. Run monitoring manually with: python3 monitor_domains.py --continuous"
fi

# Test the monitoring script
echo "Testing domain monitoring..."
python3 /app/monitor_domains.py

if [ $? -eq 0 ]; then
    echo "✓ Domain monitoring setup completed successfully"
else
    echo "⚠ Domain monitoring test had warnings or errors. Check logs for details."
fi

echo "Monitoring setup complete!"
echo "Log files are located in /app/logs/"
echo "- domain_monitoring.log: Monitoring activity log"
echo "- domain_monitoring_results.json: Latest monitoring results"
echo "- landing.log: Landing page access log"
echo "- domain_routing.log: Domain routing decisions log"
echo "- security.log: Security-related events log"