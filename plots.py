import pandas as pd
import matplotlib.pyplot as plt

import argparse
import re

def block_size_bytes(block_size_str):
    m = re.match("([0-9]+)([MK]?)", block_size_str, re.IGNORECASE)
    if not m:
        raise
    else:
        numeric_part = int(m.group(1))
        mag_part = m.group(2)
        if not mag_part:
            return numeric_part
        elif mag_part.lower() == "k":
            return 1024 * numeric_part
        elif mag_part.lower() == "m":
            return 1024 * 1024 * numeric_part
        else:
            raise



def gen_plots(data, x_axis):
    avgs = data.groupby(["mount_path", "block_size", "mode", "io_depth", x_axis]).mean()

    agg = avgs.reset_index().groupby(["mount_path", "mode", "io_depth"])
    for name, group_data in agg:
        fig, ax = plt.subplots(2,2,sharex=True,sharey="row")
        plts = []
        block_sizes = list(group_data["block_size"].unique())
        block_sizes.sort(key=lambda x: block_size_bytes(x))
        for block_size in block_sizes:
            d = group_data[group_data["block_size"]==block_size]
            plts += [ax[0, 0].plot(d[x_axis], d["total_read_iops"])]
            ax[0, 1].plot(d[x_axis], d["total_write_iops"])
            ax[1, 0].plot(d[x_axis], d["avg_read_latency"])
            ax[1, 1].plot(d[x_axis], d["avg_write_latency"])

        # plt.xlabel("Concurrency")
        # plt.ylabel("Read iops")
        # ax[0, 0].legend()
        fig.suptitle(str(name))
        # fig.legend(plts, block_sizes)
        fig.legend(block_sizes)
        plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot file system")
    parser.add_argument("datafile", nargs="+",
        help="json of data to plot")
    parser.add_argument("--num-files", action="store_true",
        help="plot according to number of files, averaging over others")
    args = parser.parse_args()

    if len(args.datafile) == 1:
        data = pd.read_json(args.datafile[0])
    else:
        data = pd.concat([pd.read_json(datafile) for datafile in args.datafile])

    data["avg_read_latency"] = data["avg_read_latency"] / 1e6
    data["avg_write_latency"] = data["avg_write_latency"] / 1e6

    if not args.num_files:
        gen_plots(data, "num_clients")
    else:
        gen_plots(data, "files_per_client")
