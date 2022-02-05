import base64
from tokenize import group

from algosdk.future import transaction
from algosdk import account, mnemonic, logic
from algosdk.v2client import algod
from algosdk.logic import get_application_address

from contracts import *

def compile_program(client, source_code):
    compile_response = client.compile(source_code)
    return base64.b64decode(compile_response['result'])

def wait_for_confirmation(client, transaction_id, timeout):
    """
    Wait until the transaction is confirmed or rejected, or until 'timeout'
    number of rounds have passed.
    Args:
        transaction_id (str): the transaction to wait for
        timeout (int): maximum number of rounds to wait    
    Returns:
        dict: pending transaction information, or throws an error if the transaction
            is not confirmed or rejected in the next timeout rounds
    """
    start_round = client.status()["last-round"] + 1
    current_round = start_round

    while current_round < start_round + timeout:
        try:
            pending_txn = client.pending_transaction_info(transaction_id)
        except Exception:
            return
        if pending_txn.get("confirmed-round", 0) > 0:
            return pending_txn
        elif pending_txn["pool-error"]:
            raise Exception(
                'pool error: {}'.format(pending_txn["pool-error"]))
        client.status_after_block(current_round)
        current_round += 1
    raise Exception(
        'pending tx not found in timeout rounds, timeout value = : {}'.format(timeout))

def create_app(client, private_key, approval_program, clear_program, global_schema, local_schema):

    sender = account.address_from_private_key(private_key)

    on_complete = transaction.OnComplete.NoOpOC.real

    params = client.suggested_params()

    txn = transaction.ApplicationCreateTxn(sender, params, on_complete,
                                           approval_program, clear_program,
                                           global_schema, local_schema)

    return exec_txn(client, txn, private_key)

    # signed_txn = txn.sign(private_key)
    # tx_id = signed_txn.transaction.get_txid()

    # client.send_transactions([signed_txn])

    # wait_for_confirmation(client, tx_id, 5)

    # transaction_response = client.pending_transaction_info(tx_id)
    # app_id = transaction_response['application-index']
    # print("Created new app-id:", app_id)

    # return app_id

def exec_txn(client, txn, private_key):
    signed_txn = txn.sign(private_key)
    tx_id = signed_txn.transaction.get_txid()
    print("Txn id:", tx_id)
    client.send_transactions([signed_txn])
    wait_for_confirmation(client, tx_id, 10)
    return client.pending_transaction_info(tx_id)


def exec_gtxn(client, txns, private_key):
    stxns = []
    for txn in txns:
        stxns.append(txn.sign(private_key))

    tx_id = client.send_transactions(stxns)
    print("Group txn id:", tx_id)

    wait_for_confirmation(client, tx_id, 10)


ALGOD_TOKEN = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
ALGOD_ADDRESS = "http://localhost:4001"

algod_client = algod.AlgodClient(ALGOD_TOKEN, ALGOD_ADDRESS)

# TODO replace with "insert your mnemonic"
MNEMONIC = "hedgehog task anchor bird student radio increase cause mix guess dog uncle above divorce acoustic amateur test pledge kit valid stage brave replace about easily"

pkey = mnemonic.to_private_key(MNEMONIC)

compiled_approval = compile_program(algod_client, approval_program())
compiled_clearstate = compile_program(algod_client, clear_state_program())

# no ints or bytes stored in global or local state
global_schema = transaction.StateSchema(0, 0)
local_schema = transaction.StateSchema(0, 0)


# app_id = create_app(algod_client, pkey, compiled_approval, compiled_clearstate, global_schema, local_schema)

# print(app_id['application-index'])

APP_ID = 67388770

sender = account.address_from_private_key(pkey)

updateTxn = transaction.ApplicationUpdateTxn(sender, algod_client.suggested_params(), 
    APP_ID, compiled_approval, compiled_clearstate)

exec_txn(algod_client, updateTxn, pkey)

noopTxn = transaction.ApplicationNoOpTxn(sender, algod_client.suggested_params(), APP_ID, [0])

noopTxn2 = transaction.ApplicationNoOpTxn(sender, algod_client.suggested_params(), APP_ID, [1])

# exec_txn(algod_client, noopTxn, pkey)

# optInTxn = transaction.ApplicationCloseOutTxn(sender, algod_client.suggested_params(), APP_ID)

# exec_txn(algod_client, optInTxn, pkey)

groupTxnId = transaction.calculate_group_id([noopTxn2, noopTxn])

noopTxn.group = groupTxnId
noopTxn2.group = groupTxnId

exec_gtxn(algod_client, [noopTxn2, noopTxn], pkey)
