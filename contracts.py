from pyteal import *

def approval_program():

    i = ScratchVar(TealType.uint64)
    test = ScratchVar(TealType.bytes)

    handle_noop=Seq([
        test.store(Bytes("1")),
        
        For(i.store(Int(0)), i.load() < Int(7000), i.store(i.load() + Int(2))).Do(
            test.store(Concat(test.load(), Bytes("2")))
        ),

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