#!/usr/bin/env python3
"""generate_shortcut.py — Build SlackClaw.shortcut with per-project channel routing.

Usage:
    python3 tools/generate_shortcut.py [--token SLACK_TOKEN] [--out PATH]

The shortcut asks:
  1. Which project? (menu with one entry per app)
  2. What would you like to say?

It then POSTs  @SlackClaw <message>  to the right Slack channel and shows a
confirmation notification.

Token placeholder is "SLACK_TOKEN_HERE" by default; replace via --token or
edit the first Text action inside the Shortcuts app after import.

Channel IDs are placeholders (e.g. DAYIST_CHANNEL_ID).  Edit the per-project
Text actions, or update the PROJECTS list below before generating.
"""

import argparse
import os
import plistlib
import uuid


# ── project → Slack channel ID ──────────────────────────────────────────────
PROJECTS = [
    ("Dayist",          "DAYIST_CHANNEL_ID"),
    ("NOVA",            "NOVA_CHANNEL_ID"),
    ("Nudge",           "NUDGE_CHANNEL_ID"),
    ("TileDock",        "TILEDOCK_CHANNEL_ID"),
    ("Atmos Universal", "ATMOS_CHANNEL_ID"),
    ("SidePlane",       "SIDEPLANE_CHANNEL_ID"),
    ("SlackClaw",       "SLACKCLAW_CHANNEL_ID"),
]

SLACK_API_URL = "https://slack.com/api/chat.postMessage"


# ── plist helpers ────────────────────────────────────────────────────────────

def uid() -> str:
    return str(uuid.uuid4()).upper()


def plain(s: str) -> dict:
    """Wrap a plain string in a WFTextTokenString."""
    return {
        "Value": {"attachmentsByRange": {}, "string": s},
        "WFSerializationType": "WFTextTokenString",
    }


def var_ref(var_name: str) -> dict:
    """A WFTextTokenString that is purely a variable reference."""
    return {
        "Value": {
            "attachmentsByRange": {"{0, 1}": {"Type": "Variable", "VariableName": var_name}},
            "string": "\uFFFC",
        },
        "WFSerializationType": "WFTextTokenString",
    }


def prefixed_var(prefix: str, var_name: str) -> dict:
    """'<prefix><var>' as a WFTextTokenString (e.g. 'Bearer <token>')."""
    pos = len(prefix)
    return {
        "Value": {
            "attachmentsByRange": {
                f"{{{pos}, 1}}": {"Type": "Variable", "VariableName": var_name}
            },
            "string": prefix + "\uFFFC",
        },
        "WFSerializationType": "WFTextTokenString",
    }


def output_attach(output_name: str, output_uuid: str) -> dict:
    """WFTextTokenAttachment pointing at a named action output."""
    return {
        "Value": {
            "Type": "ActionOutput",
            "OutputName": output_name,
            "OutputUUID": output_uuid,
        },
        "WFSerializationType": "WFTextTokenAttachment",
    }


def dict_value(pairs: list) -> dict:
    """Build a WFDictionaryFieldValue from [(key_str, value_wftts), …]."""
    return {
        "Value": {
            "WFDictionaryFieldValueItems": [
                {"WFItemType": 0, "WFKey": plain(k), "WFValue": v}
                for k, v in pairs
            ]
        },
        "WFSerializationType": "WFDictionaryFieldValue",
    }


# ── action builders ──────────────────────────────────────────────────────────

def act_text(wftts: dict, output_uuid: str) -> dict:
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.text",
        "WFWorkflowActionParameters": {
            "WFTextActionText": wftts,
            "UUID": output_uuid,
        },
    }


def act_set_var(var_name: str, input_value: dict) -> dict:
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.setvariable",
        "WFWorkflowActionParameters": {
            "WFVariableName": var_name,
            "WFInput": input_value,
        },
    }


def act_ask(prompt: str, output_uuid: str) -> dict:
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.ask",
        "WFWorkflowActionParameters": {
            "WFAskActionPrompt": prompt,
            "WFInputType": "Text",
            "UUID": output_uuid,
            "CustomOutputName": "Provided Input",
        },
    }


def act_menu_start(prompt: str, items: list, group_uuid: str) -> dict:
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.choosefrommenu",
        "WFWorkflowActionParameters": {
            "WFMenuPrompt": prompt,
            "WFMenuItems": items,
            "GroupingIdentifier": group_uuid,
            "WFControlFlowMode": 0,
        },
    }


def act_menu_case(title: str, group_uuid: str) -> dict:
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.choosefrommenu",
        "WFWorkflowActionParameters": {
            "WFMenuItemTitle": title,
            "GroupingIdentifier": group_uuid,
            "WFControlFlowMode": 1,
        },
    }


def act_menu_end(group_uuid: str) -> dict:
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.choosefrommenu",
        "WFWorkflowActionParameters": {
            "GroupingIdentifier": group_uuid,
            "WFControlFlowMode": 2,
        },
    }


def act_http_post(url: str, headers_dict: dict, body_dict: dict) -> dict:
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
        "WFWorkflowActionParameters": {
            "WFHTTPMethod": "POST",
            "WFURL": url,
            "WFHTTPHeaders": headers_dict,
            "WFHTTPBodyType": "JSON",
            "WFHTTPRequestJSONValues": body_dict,
            "WFShowHeaders": False,
        },
    }


def act_notify(title: str, body_wftts: dict) -> dict:
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.notification",
        "WFWorkflowActionParameters": {
            "WFNotificationActionTitle": title,
            "WFNotificationActionBody": body_wftts,
            "WFNotificationActionSound": True,
        },
    }


# ── shortcut assembly ────────────────────────────────────────────────────────

def build_shortcut(token: str) -> dict:
    actions = []

    # ── 0: Token text (import question targets this action) ──────────────────
    token_text_uuid = uid()
    actions.append(act_text(plain(token), token_text_uuid))
    # index 0  ← WFWorkflowImportQuestions ActionIndex

    # ── 1: Save token to named variable ─────────────────────────────────────
    actions.append(act_set_var("SlackToken", output_attach("Text", token_text_uuid)))

    # ── 2: Ask for the message ───────────────────────────────────────────────
    ask_uuid = uid()
    actions.append(act_ask("What would you like to say?", ask_uuid))

    # ── 3: Save user input to named variable ────────────────────────────────
    actions.append(act_set_var("UserMessage", output_attach("Provided Input", ask_uuid)))

    # ── 4: Channel routing menu ──────────────────────────────────────────────
    menu_uuid = uid()
    project_names = [name for name, _ in PROJECTS]
    actions.append(act_menu_start("Which project?", project_names, menu_uuid))

    for name, channel_id in PROJECTS:
        actions.append(act_menu_case(name, menu_uuid))
        ch_text_uuid = uid()
        actions.append(act_text(plain(channel_id), ch_text_uuid))
        actions.append(act_set_var("ChannelID", output_attach("Text", ch_text_uuid)))

    actions.append(act_menu_end(menu_uuid))

    # ── 5: HTTP POST to Slack ────────────────────────────────────────────────
    headers = dict_value([
        ("Authorization", prefixed_var("Bearer ", "SlackToken")),
        ("Content-Type",  plain("application/json")),
    ])
    body = dict_value([
        ("channel", var_ref("ChannelID")),
        ("text",    prefixed_var("@SlackClaw ", "UserMessage")),
    ])
    actions.append(act_http_post(SLACK_API_URL, headers, body))

    # ── 6: Confirmation notification ─────────────────────────────────────────
    actions.append(act_notify("SlackClaw", plain("Message sent \u2713")))

    # ── Import question: prompt for Slack token on first import ──────────────
    import_questions = [
        {
            "ActionIndex": 0,           # the token Text action above
            "Category": "Parameter",
            "DefaultValue": "xoxb-YOUR-TOKEN-HERE",
            "ParameterKey": "WFTextActionText",
            "Text": "Paste your Slack Bot Token (xoxb-\u2026)",
        }
    ]

    return {
        "WFWorkflowActions": actions,
        "WFWorkflowClientVersion": "1140.5",
        "WFWorkflowHasShortcutInputVariables": False,
        "WFWorkflowIcon": {
            "WFWorkflowIconGlyphNumber": 59511,      # speech bubble glyph
            "WFWorkflowIconStartColor": 431817727,   # Slack purple-ish
        },
        "WFWorkflowImportQuestions": import_questions,
        "WFWorkflowInputContentItemClasses": [],
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowName": "SlackClaw",
        "WFWorkflowTypes": [],
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token",  default="SLACK_TOKEN_HERE",
                        help="Slack bot token (xoxb-…); can also be edited inside Shortcuts")
    parser.add_argument("--out", default="shortcuts/SlackClaw.shortcut",
                        help="Output path for the .shortcut file")
    args = parser.parse_args()

    shortcut = build_shortcut(args.token)

    out_path = args.out
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    with open(out_path, "wb") as fh:
        plistlib.dump(shortcut, fh, fmt=plistlib.FMT_BINARY)

    print(f"Written: {out_path}")
    print()
    print("Next steps")
    print("──────────")
    print("1. AirDrop or share the .shortcut file to your iPhone.")
    print("2. Tap it — Shortcuts will ask you to paste your Slack Bot Token.")
    print("   (If it doesn't ask, open the shortcut and edit the first 'Text' action.)")
    print("3. Replace each  *_CHANNEL_ID  placeholder in the project Text actions")
    print("   with the real Slack channel ID (Settings › channel › Copy channel ID).")
    print("4. Add 'SlackClaw' to your Home Screen or ask Siri: 'Run SlackClaw'.")
    print()
    print("Note: iOS will warn about 'untrusted shortcuts' on first import.")
    print("Allow it via Settings › Shortcuts › Allow Untrusted Shortcuts.")


if __name__ == "__main__":
    main()
