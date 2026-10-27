from chariot.awm import workflows
from chariot.client import connect

from ticketlog.packages.chariot.runs import run

WORKFLOW_ID = "3HSVWgNybiY1fYhfkuvoNVS6KdM"

connect(credentials="ticket-log.json")
agent_name = workflows.get_workflow_agents(WORKFLOW_ID)[0]

with run(WORKFLOW_ID, "Hello", agent_name) as stream:
    for activity in stream:
        if activity.type == "agent_to_user_message":
            print(activity.body)
        elif activity.type == "error":
            raise RuntimeError(activity.body)
