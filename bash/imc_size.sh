work_dir='/home/rbp5354/trojanzoo'
cd $work_dir

dataset='cifar10'
model='resnetcomp18'
attack='imc'

CUDA_VISIBLE_DEVICES=2,3

dirname=${work_dir}/result/${dataset}/${model}/${attack}
if [ ! -d $dirname  ];then
    mkdir -p $dirname
fi

alpha=0.0
for size in {1..3}
do
    echo $size
    CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES python ${work_dir}/backdoor_attack.py --attack $attack --mark_alpha $alpha --height $size --width $size \
    --percent 0.05 --verbose --pretrain --validate_interval 1 --lr_scheduler --step_size 10 --epoch 50 --lr 1e-2 --save \
    > $dirname/size${size}.txt 2>&1
done

alpha=0.0
for size in {4..7}
do
    echo $size
    CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES python ${work_dir}/backdoor_attack.py --attack $attack --mark_alpha $alpha --height $size --width $size \
    --percent 0.02 --verbose --pretrain --validate_interval 1 --lr_scheduler --step_size 10 --epoch 50 --lr 1e-2 --save \
    > $dirname/size${size}.txt 2>&1
done