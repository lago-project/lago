from utils import run_command, run_command_with_validation


def convert(src, dst, convert_format='raw'):
    result = run_command_with_validation(
        [
            'qemu-img',
            'convert',
            '-O',
            convert_format,
            src,
            dst,
        ],
        msg='qemu-img convert failed:'
    )
    return result
