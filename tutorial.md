# 1. Python SDK Setup

For this project, you'll want to have two files: `contracts.py` and `testing.py`. Below is some Algorand Python SDK boilerplate for executing transactions, which should go in `testing.py`.

```python
    import base64

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

    def exec_txn(client, txn, private_key):
        signed_txn = txn.sign(private_key)
        tx_id = signed_txn.transaction.get_txid()

        client.send_transactions([signed_txn])
        wait_for_confirmation(client, tx_id, 10)
        return client.pending_transaction_info(tx_id)


    def exec_gtxn(client, txns, private_key):
        stxns = []
        for txn in txns:
            stxns.append(txn.sign(private_key))

        tx_id = client.send_transactions(stxns)

        wait_for_confirmation(client, tx_id, 10)


    ALGOD_TOKEN = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    ALGOD_ADDRESS = "http://localhost:4001"

    algod_client = algod.AlgodClient(ALGOD_TOKEN, ALGOD_ADDRESS)

    MNEMONIC = "YOUR_MNEMONIC_HERE" # replace with your own mnemonic

    pkey = mnemonic.to_private_key(MNEMONIC)

    compiled_approval = compile_program(algod_client, approval_program())
    compiled_clearstate = compile_program(algod_client, clear_state_program())

    global_schema = transaction.StateSchema(0, 0) # no ints or bytes stored in global or local state
    local_schema = transaction.StateSchema(0, 0)
```

`compile_program`, `wait_for_confirmation`, and `create_app` are all taken from Algorand's PyTEAL overview [here](https://developer.algorand.org/docs/get-details/dapps/pyteal/#deploying-and-calling-the-smart-contract). I've also added two new functions: `exec_txn` and `exec_gtxn`, which call an arbitrary transaction and grouped transactions (given an array of transactions), respectively. `create_app` has been modified to use `exec_txn` to avoid redundancy. One side note: I've changed the `wait_rounds` parameter in `wait_for_confirmation()` to 10, since I've personally found that the maximum 5 block rounds Algorand uses in their example code is sometimes insufficient.

As you might have noticed, we are importing from `contracts.py` at the top, as well as calling undefined functions `approval_program()` and `clear_state_program()`. Let's go make them.

# 2. Creating and Executing an Empty Contract

In `contracts.py`, create the following two functions:

```python

    from pyteal import *

    def approval_program():
        return compileTeal(Approve(), Mode.Application, version=5)

    def clear_state_program():
        return compileTeal(Approve(), Mode.Application, version=5)


```

These two basic functions handle every potential app call with an `Approve()` statement. You may see some examples using `Return(Int(1))` as a default approval return value; this has now been replaced by the equivalent `Approve()` statement (with `Reject()` corresponding to `Return(Int(0))`).

Now try running `testing.py`. You should get nothing in return. Fantastic!

Next, let's properly set up our `approval_program()` to handle different app calls:

```python
    def approval_program():

        handle_noop=Seq([
            Approve(),
        ])

        program = Cond(
            [Txn.application_id() == Int(0), Approve()],
            [Txn.on_completion() == OnComplete.OptIn, Reject()],
            [Txn.on_completion() == OnComplete.CloseOut, Reject()],
            [Txn.on_completion() == OnComplete.UpdateApplication, Reject()],
            [Txn.on_completion() == OnComplete.DeleteApplication, Reject()],
            [Txn.on_completion() == OnComplete.NoOp, handle_noop]
        )

        return compileTeal(program, Mode.Application, version=5)
```

Here, we've (obviously) allowed for app creation (when an app call transaction is sent with an application ID of 0). Update and delete transactions are not allowed, and opt in/close out calls are also rejected since our smart contract will not be dealing with local state. The most important transaction type to handle here is a NoOp transaction, which we've fed through to an empty `Seq()` right now.

Now, let's deploy and execute this smart contract with the Python SDK. At the bottom of `testing.py`, add the following:

```python
    createAppTxn = create_app(algod_client, pkey, compiled_approval, compiled_clearstate, global_schema, local_schema)

    app_id = createAppTxn['application-index']

    sender = account.address_from_private_key(pkey)

    noopTxn = transaction.ApplicationNoOpTxn(sender, algod_client.suggested_params(), app_id)

    exec_txn(algod_client, noopTxn, pkey)
```

The contract will now execute the `Approve()` statement in handle_noop, but nothing should print to the console.

# 3. Opcode Overview



Let's now explore the mechanics behind the Algorand Virtual Machine (AVM) opcode budget system. We'll be working before the `Approve()` statement in the handle_noop `Seq`, as this is what will be executed during a standard app call. From the [opcode budget list](https://developer.algorand.org/docs/get-details/dapps/avm/teal/opcodes/), we see that the Keccak256 hash has a cost of 130. To test this out, add the following lines to your `Seq`:

```python
    Pop(Keccak256(Bytes("a"))),
    Pop(Keccak256(Bytes("b"))),
    Pop(Keccak256(Bytes("c"))),
    Pop(Keccak256(Bytes("d"))),
    Pop(Keccak256(Bytes("e"))),
```

There is no significance to the letters we are feeding in; the cost will be the same regardless of the input bytes. To ensure that the execution stack is clear before the `Approve()` is reached, we are popping each generated hash as we go. If we try running `testing.py` again, we see nothing happens, as expected: (5 hashes) \* (130 per hash) = 650 < 700. However if we add another hash to our `Seq`:

```python
    Pop(Keccak256(Bytes("f"))),
```

The execution fails, with "logic eval error: dynamic cost budget exceeded".

# 4. Control Flow

How are opcode budgets calculated across different potential execution paths? In previous versions of the AVM, opcode budgets were calculated line-by-line, regardless of which statements would be excecuted. For example, an If-Else pair with Keccak256 hashes in each code block would contribute 2\*130 to the overall budget, despite only one hash being computed during execution. However, the AVM now tallies opcodes as a program executes, ensuring there is sufficient budget remaining before executing each statement and failing only if the 700 budget will be exceeded.

To demonstrate, wrap the final two Keccak256 hashes in an If-Else pair:

```python
    Pop(Keccak256(Bytes("a"))),
    Pop(Keccak256(Bytes("b"))),
    Pop(Keccak256(Bytes("c"))),
    Pop(Keccak256(Bytes("d"))),
    If(Int(1)).Then(
        Pop(Keccak256(Bytes("e"))),
    ).Else(
        Pop(Keccak256(Bytes("f"))),
    ),
```

As expected, the transaction stays within its opcode budget and does not fail. While this if statement is obviously not useful, it nicely demonstrates the underlying mechanism for computing opcode usage; as either path in the if statement results in 5 total hash computations.

# 5. Expanding the budget

What if you need a budget larger than 700? As of TEAL 4, opcode budgets are shared across group transactions, so your total *shared* budget for a grouped transaction can be up to 16 * 700 = 11200 (from the 16 maximum number of transactions in an atomic transaction). To show how this works, let's first construct the following group transaction in `testing.py`:

```python
    noopTxn = transaction.ApplicationNoOpTxn(sender, algod_client.suggested_params(), APP_ID, [0])

    noopTxn2 = transaction.ApplicationNoOpTxn(sender, algod_client.suggested_params(), APP_ID, [1])

    groupTxnId = transaction.calculate_group_id([noopTxn, noopTxn2])

    noopTxn.group = groupTxnId
    noopTxn2.group = groupTxnId

    exec_gtxn(algod_client, [noopTxn, noopTxn2], pkey)
```

Here, we are creating two nearly-identical NoOp application calls, differing only by a single parameter (0 for `noopTxn` and 1 for `noopTxn2`). We then package them into a single group transaction and execute them using the helper function `exec_gtxn` provided at the beginning. Next, let's update `contracts.py` to handle these different parameters. Inside the handle_noop `Seq()`, let's modify our If-Else:

```python
    If(Btoi(Txn.application_args[0])).Then(Seq([
        Pop(Keccak256(Bytes("e"))),
        Pop(Keccak256(Bytes("f"))),
    ]))
    .Else(Seq([
        Pop(Keccak256(Bytes("g"))),
    ])),
```

The Btoi(Txn.application_args[0]) will evaluate to false (`Int(0)`) if our argument is 0, and true otherwise. From our group transaction, we see that the first NoOp transaction will evaluate to false, while the second will be true. Running `testing.py` again, we find that the execution fails: Although we have a total budget of (700-10) * 2 = 1380, the first transaction computes hashes for the letters a-d and g for an opcode cost of 5 * 130 = 650, while the second transaction computes hashes for a-f for an opcode cost of 6 * 130 = 780. The total opcode cost for the group transaction, therefore, is 650 + 780 = 1430, exceeding the 1400 limit.

However, if we remove the "g" hash in the `Else` block (just commenting it out), the execution succeeds. While the second transaction alone (the one in which the first `If` block is executed) will compute hashes for the letters a-f for an opcode cost of 6 * 130 = 780 > 700, the first transaction only computes the four hashes before the if-else block, for an opcode cost of 4 * 130 = 520. The total opcode cost for the group transaction is then 520 + 780 = 1300, which is less than the 1400 limit.

# 6. Conclusion

Congratulations! You now understand the TEAL opcode budget, and are able to use atomic transactions to increase this budget amount. TEAL is evolving rapidly, so make sure to stay informed for future changes, such as budget increases beyond the current 700 or other ways to increase the budget yourself, such as by creating "inner applications."