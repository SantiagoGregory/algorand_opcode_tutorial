from pyteal import *


def approval_program():

    i = ScratchVar(TealType.uint64)
    # test = ScratchVar(TealType.bytes)

    handle_noop = Seq([

        Pop(Keccak256(Bytes("a"))),
        Pop(Keccak256(Bytes("b"))),
        Pop(Keccak256(Bytes("c"))),
        Pop(Keccak256(Bytes("d"))),
        If(Btoi(Txn.application_args[0])).Then(Seq([
            Pop(Keccak256(Bytes("e"))),
            Pop(Keccak256(Bytes("f"))),
        ]))
        .Else(Seq([
            # Pop(Keccak256(Bytes("g"))),
        ])
        ),
        # test.store(Bytes("1")),
        # For(i.store(Int(0)), i.load() < Int(4), i.store(i.load() + Int(1))).Do(
        #     Log(Keccak256(Itob(i.load())))
        # ),

        Approve()


    ])

    program = Cond(
        [Txn.application_id() == Int(0), Approve()],
        [Txn.on_completion() == OnComplete.OptIn, Reject()],
        [Txn.on_completion() == OnComplete.CloseOut, Reject()],
        [Txn.on_completion() == OnComplete.UpdateApplication, Approve()],
        [Txn.on_completion() == OnComplete.DeleteApplication, Reject()],
        [Txn.on_completion() == OnComplete.NoOp, handle_noop]
    )

    return compileTeal(program, Mode.Application, version=5)


def clear_state_program():
    return compileTeal(Approve(), Mode.Application, version=5)
