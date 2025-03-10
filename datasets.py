import random
import copy
import torch
from torch.utils.data import Dataset
import math
import numpy as np
import random
from utils import neg_sample

class CDDRecDataset(Dataset):

    def __init__(self, args, user_seq, times_seq, id_seq, test_neg_items=None, data_type='train'):
        self.args = args
        self.user_seq = user_seq
        self.times_seq = times_seq
        self.test_neg_items = test_neg_items
        self.data_type = data_type
        self.max_len = args.max_seq_length
        self.id_seq=id_seq

    def __getitem__(self, index):

        user_id = self.id_seq[index]
        items = self.user_seq[index]
        times = self.times_seq[index]

        assert self.data_type in {"train", "valid", "test"}



        if self.data_type == "train":
            input_ids = items[:-3]
            target_pos = items[1:-2]
            input_times = times[:-3]  # 对应的时间戳
            target_times = times[1:-2]  # 目标时间戳
            answer = [0] # no use

        elif self.data_type == 'valid':
            input_ids = items[:-2]
            target_pos = items[1:-1]
            input_times = times[:-2]  # 对应的时间戳
            target_times = times[1:-1]  # 目标时间戳
            answer = [items[-2]]

        else:
            input_ids = items[:-1]
            target_pos = items[1:]
            input_times = times[:-1]  # 对应的时间戳
            target_times = times[1:]  # 目标时间戳
            answer = [items[-1]]


        target_neg = []
        seq_set = set(items)
        for _ in input_ids:
            target_neg.append(neg_sample(seq_set, self.args.item_size))

        if self.args.data_augmentation:
            dice = random.sample(range(3), k=1)
            copy_input_ids = copy.deepcopy(input_ids)
            copy_input_times = copy.deepcopy(input_times)  # 同样复制时间戳
            # if dice == 0:
            #     aug_input_ids = self.item_crop(copy_input_ids)
            # elif dice ==1:
            #     aug_input_ids = self.item_mask(copy_input_ids)
            # else:
            #     aug_input_ids = self.item_reorder(copy_input_ids)
            if dice == 0:
                aug_input_ids, aug_input_times = self.item_crop(copy_input_ids, copy_input_times)
            elif dice == 1:
                aug_input_ids, aug_input_times = self.item_mask(copy_input_ids, copy_input_times)
            else:
                aug_input_ids, aug_input_times = self.item_reorder(copy_input_ids, copy_input_times)
        else:
            # 生成与 input_ids 相同长度的全零序列
            aug_input_ids = [0] * self.max_len
            aug_input_times = [0] * self.max_len


        # add 0 ids from the start
        pad_len = self.max_len - len(input_ids)
        input_ids = [0] * pad_len + input_ids
        target_pos = [0] * pad_len + target_pos
        target_neg = [0] * pad_len + target_neg
        input_times = [0] * pad_len + input_times  # 时间戳填充
        target_times = [0] * pad_len + target_times

        # for long sequences that longer than max_len
        input_ids = input_ids[-self.max_len:]
        target_pos = target_pos[-self.max_len:]
        target_neg = target_neg[-self.max_len:]
        input_times = input_times[-self.max_len:]
        target_times = target_times[-self.max_len:]

        if self.args.data_augmentation:
            # add 0 ids from the start
            aug_pad_len = self.max_len - len(aug_input_ids)
            aug_input_ids = [0] * aug_pad_len + aug_input_ids
            aug_input_times = [0] * aug_pad_len + aug_input_times  # 增强数据的时间戳填充

            # for long sequences that longer than max_len
            aug_input_ids = aug_input_ids[-self.max_len:]
            aug_input_times = aug_input_times[-self.max_len:]
        else: 
            aug_input_ids = [0] * self.max_len
            aug_input_times = [0] * self.max_len

        assert len(input_ids) == self.max_len
        assert len(target_pos) == self.max_len
        assert len(target_neg) == self.max_len
        assert len(input_times) == self.max_len
        assert len(target_times) == self.max_len

        if self.test_neg_items is not None:
            test_samples = self.test_neg_items[index]

            cur_tensors = (
                torch.tensor(user_id, dtype=torch.long), # user_id for testing
                torch.tensor(input_ids, dtype=torch.long),
                torch.tensor(target_pos, dtype=torch.long),
                torch.tensor(target_neg, dtype=torch.long),
                torch.tensor(answer, dtype=torch.long),
                torch.tensor(test_samples, dtype=torch.long),
                torch.tensor(aug_input_ids,dtype=torch.long),
                torch.tensor(input_times, dtype=torch.long),  # 添加时间戳
                torch.tensor(aug_input_times, dtype=torch.long),  # 添加增强数据的时间戳
                torch.tensor(target_times, dtype=torch.long)  # 添加目标时间戳
            )
        else: # all of shape: b*max_sq
            cur_tensors = (
                torch.tensor(user_id, dtype=torch.long),  # user_id for testing
                torch.tensor(input_ids, dtype=torch.long), # training
                torch.tensor(target_pos, dtype=torch.long), # targeting, one item right-shifted, since task is to predict next item
                torch.tensor(target_neg, dtype=torch.long), # random sample an item out of training and eval for every training items.
                torch.tensor(answer, dtype=torch.long), # last item for prediction.
                torch.tensor(aug_input_ids,dtype=torch.long),
                torch.tensor(input_times, dtype=torch.long),  # 添加时间戳
                torch.tensor(aug_input_times, dtype=torch.long),  # 添加增强数据的时间戳
                torch.tensor(target_times, dtype=torch.long)  # 添加目标时间戳
            )

        return cur_tensors

    def item_crop(self, item_seq, times_seq, eta=0.6):  # item_Seq: [batch, max_seq]
        item_seq = np.array(item_seq)
        times_seq = np.array(times_seq)
        item_seq_len = len(item_seq)
        num_left = math.floor(item_seq_len * eta)
        crop_begin = random.randint(0, item_seq_len - num_left)
        croped_item_seq = np.zeros(item_seq.shape[0])
        croped_times_seq = np.zeros(times_seq.shape[0])
        if crop_begin + num_left < item_seq.shape[0]:
            croped_item_seq[:num_left] = item_seq[crop_begin:crop_begin + num_left]
            croped_times_seq[:num_left] = times_seq[crop_begin:crop_begin + num_left]
        else:
            croped_item_seq[:num_left] = item_seq[crop_begin:]
            croped_times_seq[:num_left] = times_seq[crop_begin:]
        return list(croped_item_seq), list(croped_times_seq)


    def item_mask(self, item_seq, times_seq,  gamma=0.3):
        item_seq = np.array(item_seq)
        times_seq = np.array(times_seq)
        item_seq_len = len(item_seq)
        num_mask = math.floor(item_seq_len * gamma)
        mask_index = random.sample(range(item_seq_len), k=num_mask)
        masked_item_seq = item_seq.copy()
        masked_times_seq = times_seq.copy()
        masked_item_seq[mask_index] = self.args.mask_id  # token 0 has been used for semantic masking
        masked_times_seq[mask_index] = 0  # 时间戳掩码为 0
        return list(masked_item_seq), list(masked_times_seq)


    def item_reorder(self, item_seq, times_seq,  beta=0.6):
        item_seq = np.array(item_seq)
        times_seq = np.array(times_seq)
        item_seq_len = len(item_seq)
        num_reorder = math.floor(item_seq_len * beta)
        reorder_begin = random.randint(0, item_seq_len - num_reorder)
        reordered_item_seq = item_seq.copy()
        reordered_times_seq = times_seq.copy()
        shuffle_index = list(range(reorder_begin, reorder_begin + num_reorder))
        random.shuffle(shuffle_index)
        reordered_item_seq[reorder_begin:reorder_begin + num_reorder] = reordered_item_seq[shuffle_index]
        reordered_times_seq[reorder_begin:reorder_begin + num_reorder] = reordered_times_seq[shuffle_index]
        return list(reordered_item_seq), list(reordered_times_seq)


    def __len__(self):
        return len(self.user_seq)
