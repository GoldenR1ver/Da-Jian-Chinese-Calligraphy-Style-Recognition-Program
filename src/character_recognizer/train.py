import torch
import os
from matplotlib import pyplot as plt
from torch import nn, optim
from torch.utils.data import DataLoader
from torchvision import transforms
from .MyDataset import MyDataset
from .config import args
import time
from .model import LeNet, VGG, ResNet, CNN, ResNet18, ResNet34
from .test import test as ts

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
# 强制使用模块内 data 目录，避免从“主目录/其它目录”运行时路径变化
DATA_DIR = os.path.join(MODULE_DIR, "data")


def main():
    # 获取训练集
    transform = transforms.ToTensor()

    train_dir = os.path.join(DATA_DIR, "HWDB1.1trn_gnt")

    print(f"Loading train dataset from: {train_dir}", flush=True)
    train_set = MyDataset(train_dir, transforms=transform, augment=False)
    print(f"Train samples: {len(train_set)}", flush=True)
    if len(train_set) == 0:
        raise ValueError(
            f"Train dataset is empty. Please check that {train_dir} contains valid '*.gnt' files."
        )

    # Windows 使用 spawn 启动 DataLoader worker；训练入口必须在 `if __name__ == '__main__'`
    # 中，否则子进程会重复执行模块顶层代码并触发 RuntimeError。
    num_workers = min(16, (os.cpu_count() or 1))

    train_loader = DataLoader(
        train_set,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
    )

    # 定义model 、loss 、optimizer
    torch.manual_seed(args.seed)  # 设置随机数种子，确保结果可重复
    device = torch.device(
        "cuda" if (args.cuda and torch.cuda.is_available()) else "cpu"
    )
    print(f"Device: {device}", flush=True)

    model_dict = {
        "LeNet": LeNet,
        "VGG": VGG,
        "ResNet": ResNet,
        "CNN": CNN,
        "ResNet18": ResNet18,
        "ResNet34": ResNet34,
    }

    model = model_dict[args.model]().to(device)

    param_dir = os.path.join(args.result, "param")
    model_path = os.path.join(param_dir, "model.pth")
    fig_dir = os.path.join(args.result, "fig")
    os.makedirs(param_dir, exist_ok=True)
    os.makedirs(fig_dir, exist_ok=True)

    if args.load_state:
        model.load_state_dict(torch.load(model_path, map_location=device))  # 继续训练

    model.train()
    loss_fn = nn.CrossEntropyLoss()
    optimizer = optim.SGD(model.parameters(), lr=args.lr)
    scheduler = optim.lr_scheduler.MultiStepLR(
        optimizer, milestones=[10, 20, 50], gamma=0.1
    )

    start_time = time.time()
    train_losses, train_accuracies, test_accuracies = [], [], []
    # 开始训练
    for epoch in range(1, args.epochs + 1):
        running_loss = 0.0
        running_acc = 0.0
        seen_samples = 0
        log_every = max(1, len(train_loader) // 10)  # 约每 10 次打印一次

        num_batches = len(train_loader)
        print(f"Epoch {epoch}/{args.epochs} - {num_batches} batches", flush=True)

        for batch_idx, data in enumerate(train_loader, start=1):
            image, label = data
            image, label = image.to(device), label.to(device)

            out = model(image)
            loss = loss_fn(out, label)
            running_loss += loss.item() * label.size(0)
            _, pred = torch.max(out, 1)
            num_correct = (pred == label).sum()
            running_acc += num_correct.item()
            seen_samples += label.size(0)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            if batch_idx == 1 or batch_idx % log_every == 0 or batch_idx == num_batches:
                avg_loss = running_loss / max(1, seen_samples)
                avg_acc = running_acc / max(1, seen_samples)
                print(
                    f"  Batch {batch_idx}/{num_batches} - Loss: {avg_loss:.4f}, Acc: {avg_acc:.4f}",
                    flush=True,
                )

        if epoch % 5 == 0:
            torch.save(model.state_dict(), model_path)

        test_acc, f1, recall = ts(model)

        train_loss = running_loss / (len(train_set))
        train_acc = running_acc / (len(train_set))

        train_losses.append(train_loss)
        train_accuracies.append(train_acc)
        test_accuracies.append(test_acc)

        print(
            "Train {} epoch, Loss: {:.4f}, Train_Acc: {:.4f}, Test_Acc:{:.4f}".format(
                epoch, train_loss, train_acc, test_acc
            ),
            flush=True,
        )

    end_time = time.time()
    total_time = end_time - start_time
    hours = int(total_time // 3600)
    minutes = int((total_time % 3600) // 60)
    seconds = int(total_time % 60)
    print(
        f"\n训练总耗时：{hours:02d}:{minutes:02d}:{seconds:02d}（时:分:秒）",
        flush=True,
    )

    epochs = range(1, args.epochs + 1)
    plt.plot(epochs, train_losses, label="Train Loss")
    plt.plot(epochs, train_accuracies, label="Train Accuracy")
    plt.plot(epochs, test_accuracies, label="Test Accuracy")
    plt.xlabel("Epoch")
    plt.ylabel("Value")
    plt.title("Training & Test Metrics")
    plt.legend()
    plt.grid(True)
    plt.savefig(os.path.join(fig_dir, f"{args.model}.png"))
    plt.close()


if __name__ == "__main__":
    main()
